"""Closed-form, identity and refusal tests for relief_valve R2 (line-loss checks).

Constants verified by the independent scratch script before being typed; the
Colebrook numbers reproduce through the repo's ``darcy_colebrook`` (fluids),
hence the 1e-9 tolerance on that block.
"""

from __future__ import annotations

from typing import Any

import pytest

from fluids.safety_valve import API520_B

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow import relief_valve_r1 as rv1
from ngdesign.units.flow import relief_valve_r2 as rv2
from tests.conftest import flash_feed


def _solve(thermo: Thermo, feeds: dict[str, dict[str, Any]], params: dict[str, Any]) -> Any:
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return rv2.ReliefValveR2().solve(inlets, params, thermo)


# --- closed form: inlet loss (eq. 7) ---------------------------------------


def test_r2_inlet_loss_closed_form() -> None:
    """W_rated 11.25 kg/s through rho 50, D 0.1023, L 2.0, eps 4.57e-5, K 0.5.

    Expected values from the independent script (its own Colebrook call
    reproduced the spec's f to 2e-15): v 27.3741958001557, Re 11668250.9598164,
    f 0.0163346296356747, dP 15349.3833307729 Pa.
    """
    res = rv2.inlet_line_dP(11.25, 50.0, 1.2e-5, 0.1023, 2.0, 4.57e-5, 0.5)
    assert res["velocity_m_s"] == pytest.approx(27.3741958001557, rel=1e-9)
    assert res["Re"] == pytest.approx(11668250.9598164, rel=1e-9)
    assert res["darcy_f"] == pytest.approx(0.0163346296356747, rel=1e-9)
    assert res["dP_Pa"] == pytest.approx(15349.3833307729, rel=1e-9)


def test_r2_inlet_loss_frac_of_set_gauge() -> None:
    """The closed-form dP is 0.0170800159465578 of the set gauge (1e6 - 101325)."""
    frac = 15349.3833307729 / (1.0e6 - 101325.0)
    assert frac == pytest.approx(0.0170800159465578, rel=1e-12)


def test_mcadams_viscosity() -> None:
    """1/mu = x/mu_g + (1-x)/mu_l (McAdams 1942)."""
    mu = rv2.mcadams_viscosity(0.2, 1.0e-5, 1.0e-3)
    assert mu == pytest.approx(1.0 / (0.2 / 1.0e-5 + 0.8 / 1.0e-3), rel=1e-15)


# --- identities --------------------------------------------------------------


def test_r2_zero_lines_identity(thermo: Thermo) -> None:
    """Zero-length lines give dP 0 and every R1 info value unchanged."""
    feeds, params_r0 = rv1.ReliefValveR1.example_case()
    P_set = 0.9 * feeds["inlet"]["P"]
    P_back = 0.5 * feeds["inlet"]["P"]
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    r1 = rv1.ReliefValveR1().solve(inlets, {"P_back": P_back}, thermo)
    r2 = rv2.ReliefValveR2().solve(inlets, {"P_back": P_back, "P_set": P_set}, thermo)
    assert r2.info["dP_inlet_Pa"] == 0.0
    assert r2.info["dP_builtup_Pa"] == 0.0
    for key, value in r1.info.items():
        assert r2.info[key] == value, key
    for port, state in r1.outlets.items():
        other = r2.outlets[port]
        for field in ("T", "P", "molar_flow", "vapor_fraction", "enthalpy", "entropy"):
            assert getattr(other, field) == getattr(state, field)


# --- adapter: example and checks ---------------------------------------------


def test_r2_example_checks_pass(thermo: Thermo) -> None:
    """The example solves with both checks green at the rated capacity."""
    feeds, params = rv2.ReliefValveR2.example_case()
    result = _solve(thermo, feeds, params)
    info = result.info
    assert info["inlet_loss_ok"] == 1
    assert info["backpressure_ok"] == 1
    assert info["W_rated_kg_s"] > 0.0
    assert info["inlet_loss_frac"] <= 0.03


def test_r2_conventional_over_limit_flags(thermo: Thermo) -> None:
    """A long small-bore outlet line breaks the 10 % built-up limit: ok = 0."""
    feeds, params = rv2.ReliefValveR2.example_case()
    squeezed = {**params, "L_out_m": 200.0, "D_out_m": 0.02}
    result = _solve(thermo, feeds, squeezed)
    info = result.info
    assert info["dP_builtup_Pa"] > 0.10 * (params["P_set"] - 101325.0)
    assert info["backpressure_ok"] == 0


def test_r2_bellows_uses_fig30(thermo: Thermo) -> None:
    """Balanced bellows at moderate back pressure: Kb from Fig. 30, area re-sized.

    The expected Kb is recomputed with the same fluids interpolation — a wiring
    check; the figure itself has no closed form and no fluids number is used as
    a V1 expected value.
    """
    feeds, _ = rv1.ReliefValveR1.example_case()
    P_set = 0.9 * feeds["inlet"]["P"]
    params = {
        "P_back": 0.4 * feeds["inlet"]["P"],
        "P_set": P_set,
        "valve_type": "balanced_bellows",
    }
    result = _solve(thermo, feeds, params)
    info = result.info
    frac = (info["P_back_total_Pa"] - 101325.0) / (P_set - 101325.0)
    assert 0.30 < frac <= 0.50
    assert info["backpressure_ok"] == 1
    kb = API520_B(P_set, info["P_back_total_Pa"], 0.10)
    assert info["Kb_fig30"] == pytest.approx(kb, rel=1e-12)
    assert info["area_with_backpressure_in2"] == pytest.approx(
        info["required_area_in2"] / kb, rel=1e-12
    )


def test_r2_pilot_no_limit(thermo: Thermo) -> None:
    """A pilot valve reports the values and reads not applicable (ok = 1)."""
    feeds, _ = rv1.ReliefValveR1.example_case()
    params = {
        "P_back": 0.7 * feeds["inlet"]["P"],
        "P_set": 0.9 * feeds["inlet"]["P"],
        "valve_type": "pilot",
    }
    result = _solve(thermo, feeds, params)
    assert result.info["backpressure_ok"] == 1
    assert "Kb_fig30" not in result.info
    assert "area_with_backpressure_in2" not in result.info


# --- refusals ---------------------------------------------------------------


def test_r2_refuses_missing_p_set(thermo: Thermo) -> None:
    feeds, _ = rv1.ReliefValveR1.example_case()
    with pytest.raises(rv2.ReliefValveR2Error, match="P_set"):
        _solve(thermo, feeds, {"P_back": 5.0e5})


def test_r2_refuses_p_set_range(thermo: Thermo) -> None:
    """P_set must be above atmospheric and at or below the relieving pressure."""
    feeds, _ = rv1.ReliefValveR1.example_case()
    P0 = feeds["inlet"]["P"]
    with pytest.raises(rv2.ReliefValveR2Error, match="P_set"):
        _solve(thermo, feeds, {"P_back": 0.5 * P0, "P_set": 2.0 * P0})
    with pytest.raises(rv2.ReliefValveR2Error, match="P_set"):
        _solve(thermo, feeds, {"P_back": 0.5 * P0, "P_set": 1.0e5})


def test_r2_refuses_valve_type(thermo: Thermo) -> None:
    feeds, _ = rv1.ReliefValveR1.example_case()
    P0 = feeds["inlet"]["P"]
    with pytest.raises(rv2.ReliefValveR2Error, match="valve_type"):
        _solve(
            thermo,
            feeds,
            {"P_back": 0.5 * P0, "P_set": 0.9 * P0, "valve_type": "banana"},
        )


def test_r2_refuses_line_geometry(thermo: Thermo) -> None:
    """L > 0 without D, and negative L / K / roughness, are refused by name."""
    feeds, _ = rv1.ReliefValveR1.example_case()
    P0 = feeds["inlet"]["P"]
    base = {"P_back": 0.5 * P0, "P_set": 0.9 * P0}
    with pytest.raises(rv2.ReliefValveR2Error, match="D_in_m"):
        _solve(thermo, feeds, {**base, "L_in_m": 2.0})
    with pytest.raises(rv2.ReliefValveR2Error, match="L_in_m"):
        _solve(thermo, feeds, {**base, "L_in_m": -1.0, "D_in_m": 0.1})
    with pytest.raises(rv2.ReliefValveR2Error, match="K_out"):
        _solve(thermo, feeds, {**base, "K_out": -0.5})
    with pytest.raises(rv2.ReliefValveR2Error, match="roughness_out_m"):
        _solve(
            thermo,
            feeds,
            {**base, "L_out_m": 1.0, "D_out_m": 0.1, "roughness_out_m": -1.0},
        )


def test_r2_refuses_bellows_over_50pct(thermo: Thermo) -> None:
    """Bellows total back pressure at or above 50 % of set gauge: typed refusal."""
    feeds, _ = rv1.ReliefValveR1.example_case()
    P0 = feeds["inlet"]["P"]
    params = {
        "P_back": 0.98 * P0,
        "P_set": 0.9 * P0,
        "valve_type": "balanced_bellows",
    }
    with pytest.raises(rv2.ReliefValveR2Error, match="50 %"):
        _solve(thermo, feeds, params)


def test_r2_refuses_fixedpoint_cap(monkeypatch: pytest.MonkeyPatch, thermo: Thermo) -> None:
    """A non-converging outlet line hits the 50-iteration cap: typed refusal."""
    calls = {"n": 0}

    def oscillating(*args: Any, **kwargs: Any) -> dict[str, float]:
        calls["n"] += 1
        return {
            "velocity_m_s": 1.0,
            "Re": 1.0e5,
            "darcy_f": 0.02,
            "dP_Pa": 1.0 + 0.5 * (calls["n"] % 2),
        }

    monkeypatch.setattr(rv2, "inlet_line_dP", oscillating)
    feeds, _ = rv1.ReliefValveR1.example_case()
    P0 = feeds["inlet"]["P"]
    params = {"P_back": 0.5 * P0, "P_set": 0.9 * P0, "L_out_m": 2.0, "D_out_m": 0.1}
    with pytest.raises(rv2.ReliefValveR2Error, match="back-pressure iteration"):
        _solve(thermo, feeds, params)
    assert calls["n"] >= 50


def test_mixture_viscosity_refuses_missing(thermo: Thermo) -> None:
    """A phase without viscosity is a typed refusal, not a None arithmetic error."""

    class NoMuThermo:
        """Thermo stub whose phase_props strips the viscosity."""

        def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
            base = thermo.phase_props(composition, T, P, kind)
            return base.model_copy(update={"viscosity": None})

    stream = thermo.flash_pt({"C3": 1.0}, 300.0, 1.0e5, 10.0)
    bare = stream.model_copy(
        update={"phases": [p.model_copy(update={"viscosity": None}) for p in stream.phases]}
    )
    with pytest.raises(rv2.ReliefValveR2Error, match="viscosity"):
        rv2.mixture_viscosity(bare, NoMuThermo())  # type: ignore[arg-type]
