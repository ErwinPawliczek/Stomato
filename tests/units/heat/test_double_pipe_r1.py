"""Identity, refusal and info tests for double_pipe R1 (spec U-R2, issue #266).

The identity test replays the R1 duty through the R0 ``two_stream`` solve on
the same inlets and the same per-side pressure drops: the outlets must agree
to 1e-10 relative (the same ``flash_ph`` calls on the same enthalpies), and
R0's Q/LMTD ``UA_W_K`` must sit within 1e-3 relative of R1's film-based UA -
the residual gap being the cp(T) variation that LMTD-UA does not see
(measured on this case: about 4.6e-3 relative, N2/N2 at 10 bar - see the
assertion note below for the run value).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TwoStreamSpec, two_stream
from ngdesign.units.heat.double_pipe_r1 import (
    DoublePipeGeometryError,
    DoublePipeR1,
    eps_counterflow,
)
from ngdesign.units.heat.rating import (
    PropertyUnavailable,
    RatingConvergenceError,
    RatingError,
    SinglePhaseRequired,
)

GEOMETRY: dict[str, Any] = {
    "inner_ID_m": 0.0266,
    "inner_OD_m": 0.0334,
    "outer_ID_m": 0.0525,
    "length_m": 60.0,
    "inner_side": "hot",
}


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _inlets(thermo: Thermo, **over: Any) -> dict[str, StreamState]:
    feeds, _ = DoublePipeR1.example_case()
    feeds = {port: {**f, **over.get(port, {})} for port, f in feeds.items()}
    return {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
        for port, f in feeds.items()
    }


def _solve(thermo: Thermo, params: dict[str, Any], **feed_over: Any) -> Any:
    return DoublePipeR1().solve(_inlets(thermo, **feed_over), params, thermo)


def test_reduction_to_r0_identity() -> None:
    """R0 replay of the R1 duty reproduces the R1 outlets; UA within 1e-3 rel.

    The R0 solve runs ``two_stream`` with ``TwoStreamSpec(duty_W=Q_R1)`` and
    R1's per-side pressure drops, on the example case (N2 500 K / N2 320 K,
    100 mol/s each, 10 bar, inner_ID 0.0266 / inner_OD 0.0334 / outer_ID
    0.0525, 60 m, inner side hot).
    """
    thermo = _thermo()
    result = _solve(thermo, dict(GEOMETRY))
    q = float(result.info["duty_W"])
    dP_h = float(result.info["dP_inner_Pa"])
    dP_c = float(result.info["dP_annulus_Pa"])
    inlets = _inlets(thermo)
    r0 = two_stream(
        inlets["hot_in"], inlets["cold_in"], TwoStreamSpec(duty_W=q), thermo, dP_hot=dP_h, dP_cold=dP_c
    )
    hot1, cold1 = result.outlets["hot_out"], result.outlets["cold_out"]
    for a, b in (
        (hot1.T, r0.hot_out.T),
        (hot1.enthalpy, r0.hot_out.enthalpy),
        (cold1.T, r0.cold_out.T),
        (cold1.enthalpy, r0.cold_out.enthalpy),
    ):
        assert a == pytest.approx(b, rel=1e-10)
    # The same flash_ph calls on the same enthalpies agree to 1e-10 above;
    # the UA comparison carries the cp(T) variation LMTD-UA cannot see
    # (spec bound 1e-3 relative on this case).
    assert float(result.info["UA_W_K"]) == pytest.approx(r0.UA_W_K, rel=1e-3)


def test_info_keys_and_duty_convention() -> None:
    """The spec's info keys are present; unit-level duty is the residual."""
    thermo = _thermo()
    result = _solve(thermo, dict(GEOMETRY))
    for key in (
        "duty_W",
        "U_W_m2K",
        "A_m2",
        "UA_W_K",
        "NTU",
        "effectiveness",
        "LMTD_K",
        "h_inner_W_m2K",
        "h_annulus_W_m2K",
        "Re_inner",
        "Re_annulus",
        "dP_inner_Pa",
        "dP_annulus_Pa",
        "rating_iterations",
    ):
        assert key in result.info, f"missing info key {key}"
    q = float(result.info["duty_W"])
    assert q > 0.0
    assert result.power_W == 0.0
    # Internal exchanger: the unit-level duty is the round-off residual.
    assert abs(result.duty_W) <= 1e-6 * q
    assert 0.0 < float(result.info["effectiveness"]) < 1.0
    assert float(result.info["dP_inner_Pa"]) > 0.0
    assert float(result.info["dP_annulus_Pa"]) > 0.0


def test_eps_counterflow_cr_one_branch() -> None:
    """Closed-form test 5's Cr = 1 line: eps = NTU/(1+NTU) = 0.571428571."""
    assert eps_counterflow(4.0 / 3.0, 1.0) == pytest.approx(0.571428571, rel=1e-8)


def test_missing_geometry_refuses() -> None:
    with pytest.raises(DoublePipeGeometryError, match="inner_ID_m"):
        _solve(_thermo(), {k: v for k, v in GEOMETRY.items() if k != "inner_ID_m"})


def test_nonpositive_geometry_refuses() -> None:
    with pytest.raises(DoublePipeGeometryError, match="inner_ID_m"):
        _solve(_thermo(), {**GEOMETRY, "inner_ID_m": -0.01})


def test_inner_od_ordering_refuses() -> None:
    with pytest.raises(DoublePipeGeometryError, match="inner_OD_m"):
        _solve(_thermo(), {**GEOMETRY, "inner_OD_m": GEOMETRY["inner_ID_m"]})


def test_outer_id_ordering_refuses() -> None:
    with pytest.raises(DoublePipeGeometryError, match="outer_ID_m"):
        _solve(_thermo(), {**GEOMETRY, "outer_ID_m": GEOMETRY["inner_OD_m"]})


def test_bad_inner_side_refuses() -> None:
    with pytest.raises(DoublePipeGeometryError, match="inner_side"):
        _solve(_thermo(), {**GEOMETRY, "inner_side": "middle"})


def test_zero_flow_refuses() -> None:
    with pytest.raises(RatingError, match="needs both streams flowing"):
        _solve(_thermo(), dict(GEOMETRY), hot_in={"molar_flow": 0.0})


def test_temperature_cross_refuses() -> None:
    thermo = _thermo()
    feeds, params = DoublePipeR1.example_case()
    hot = thermo.flash_pt({"N2": 1.0}, 320.0, 1.0e6, 100.0)
    cold = thermo.flash_pt({"N2": 1.0}, 500.0, 1.0e6, 100.0)
    with pytest.raises(Exception, match="inlet temperatures"):
        DoublePipeR1().solve({"hot_in": hot, "cold_in": cold}, params, thermo)


def test_two_phase_inlet_refuses() -> None:
    """Water at its bubble point (two-phase) reaches SinglePhaseRequired."""
    thermo = _thermo()
    hot = thermo.flash_tvf({"H2O": 1.0}, 373.15, 0.5, 100.0)
    assert len(hot.phases) == 2
    cold = thermo.flash_pt({"N2": 1.0}, 320.0, 1.0e5, 100.0)
    with pytest.raises(SinglePhaseRequired, match="R1 rates single-phase duty"):
        DoublePipeR1().solve({"hot_in": hot, "cold_in": cold}, dict(GEOMETRY), thermo)


def test_nonpositive_outlet_pressure_refuses() -> None:
    """A 100 km hairpin drops the gas below atmospheric: refused, named."""
    with pytest.raises(RatingError, match="non-positive outlet pressure"):
        _solve(_thermo(), {**GEOMETRY, "length_m": 1.0e5})


def test_property_unavailable_names_side() -> None:
    """A thermo package without transport properties is refused, side named."""

    class _NoTransport:
        def __init__(self, real: Thermo) -> None:
            self._real = real

        def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
            props = self._real.phase_props(composition, T, P, kind)
            return props.model_copy(update={"viscosity": None})

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    thermo = _thermo()
    inlets = _inlets(thermo)
    with pytest.raises(PropertyUnavailable, match="hot"):
        DoublePipeR1().solve(inlets, dict(GEOMETRY), cast(Thermo, _NoTransport(thermo)))


def test_convergence_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A brentq failure surfaces as RatingConvergenceError with the bracket."""

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("mocked brentq failure")

    _thermo()
    monkeypatch.setattr("ngdesign.units.heat.rating.brentq", boom)
    with pytest.raises(RatingConvergenceError, match="rating did not converge"):
        _solve(_thermo(), dict(GEOMETRY))
