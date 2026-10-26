"""Identity, refusal and closed-form tests for plate_exchanger R1 (spec).

The closed-form numbers are the spec's test table 1-4, hand-computed from the
spec's equations with geometry P1 (0.5 mm amplitude, 3.7 mm wavelength, 45 deg,
0.3 x 1.2 m plates, 50 mm ports, 51 plates => 25 channels per fluid,
A_ch = b*width = 1e-3*0.3 = 3.0e-4 m2, D_h = 0.0017223766473078426 m from
``fluids.geometry.PlateExchanger``), independent of the module under test:

Case 1 (laminar branch), m 3 kg/s, rho 990, mu 6.0e-4, k 0.63, cp 4180:
  v = 3/(990*25*3.0e-4) = 0.404040404... m/s
  Re = 990*0.404040404*0.0017223766473078426/6.0e-4 = 1148.2511
  Pr = 4180*6.0e-4/0.63 = 3.98095238
  f  = [cos45/sqrt(0.18 tan45 + 0.36 sin45 + (64/1148.2511)/cos45)
        + (1 - cos45)/sqrt(3.8*(597/1148.2511 + 3.85))]^-2 = 0.892089304
  Nu = 0.122*3.98095238^(1/3)*(0.892089304*1148.2511^2*1)^0.374 = 36.0342748
  h  = Nu*k/D_h = 36.0342748*0.63/0.0017223766473078426 = 13180.3884 W/m2K
  channel dP = f*(1.2/D_h)*990*v^2/2 = 50224.5717 Pa
  v_port = 3/(990*pi*0.05^2/4) = 1.54332066 m/s
  port dP = 1.4*990*v_port^2/2 = 1650.61419 Pa
Case 2 (turbulent branch), m 8 kg/s, same fluid:
  v = 8/7.425 = 1.07744108 m/s, Re = 3062.00293,
  f0 = (1.8*log10(3062.00293) - 1.5)^-2 (Konakov), f1 = 39*Re^-0.289,
  f = 0.857073074, Nu = 73.9326645, h = 27042.6208 W/m2K
Case 3: friction spot values f(500,45) = 1.06688451, f(500,60) = 2.3862954,
  f(2500,45) = 0.867587711, f(2500,60) = 1.94223808.
Case 4: U with both films h = 13180.3884, t_p = 0.6 mm, k_p = 16:
  U = 1/(2/13180.3884 + 0.0006/16) = 5284.2784 W/m2K.

The identity test (spec: R1 -> R0 on example_case) runs the R0 example feeds
(water 433.15 K / 303.15 K at 1 MPa, 100/150 mol/s) with geometry P1 on
``pr-peneloux`` (a volume-translated package that returns mu and k; plain
``pr`` returns the same transport properties here, with the density ~836-846
kg/m3 the spec notes instead of ~990).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross, TwoStreamSpec, two_stream
from ngdesign.units.heat.plate_exchanger_r1 import (
    PlateCorrelationRangeError,
    PlateExchangerR1,
    PlateGeometryError,
    channel_Re,
    channel_velocity,
    friction_kumar,
    friction_martin_vdi,
    nusselt_kumar,
    nusselt_martin_vdi,
    overall_u,
    plate_geometry,
    port_dP,
    port_velocity,
)
from ngdesign.units.heat.rating import (
    PropertyUnavailable,
    RatingConvergenceError,
    RatingError,
    SinglePhaseRequired,
)

GEOMETRY_P1: dict[str, Any] = {
    "amplitude_m": 5.0e-4,
    "wavelength_m": 3.7e-3,
    "chevron_angle_deg": 45.0,
    "plate_width_m": 0.3,
    "plate_length_m": 1.2,
    "port_diameter_m": 0.05,
    "n_plates": 51,
}


def test_geometry_p1() -> None:
    """Geometry P1: b = 1 mm, A_ch = 3.0e-4 m2, 25 channels/fluid, D_h from fluids."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    assert geom.b_m == pytest.approx(1.0e-3, rel=1e-8)
    assert geom.A_channel_m2 == pytest.approx(3.0e-4, rel=1e-8)
    assert geom.channels_per_fluid == pytest.approx(25.0, rel=1e-8)
    assert geom.D_h_m == pytest.approx(0.0017223766473078426, rel=1e-8)


def test_closed_form_laminar_branch() -> None:
    """Case 1: v, Re, Pr, f, Nu, h, channel dP, port v and port dP at 3 kg/s."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    v = channel_velocity(3.0, 990.0, geom.A_channel_m2, geom.channels_per_fluid)
    assert v == pytest.approx(0.404040404, rel=1e-8)
    Re = channel_Re(990.0, v, geom.D_h_m, 6.0e-4)
    assert Re == pytest.approx(1148.2511, rel=1e-8)
    Pr = 4180.0 * 6.0e-4 / 0.63
    assert Pr == pytest.approx(3.98095238, rel=1e-8)
    f = friction_martin_vdi(Re, 45.0)
    assert f == pytest.approx(0.892089304, rel=1e-8)
    Nu = nusselt_martin_vdi(Re, Pr, 45.0, f)
    assert Nu == pytest.approx(36.0342748, rel=1e-8)
    h = Nu * 0.63 / geom.D_h_m
    assert h == pytest.approx(13180.3884, rel=1e-8)
    channel_dp = f * (1.2 / geom.D_h_m) * 990.0 * v * v / 2.0
    assert channel_dp == pytest.approx(50224.5717, rel=1e-8)
    v_port = port_velocity(3.0, 990.0, 0.05)
    assert v_port == pytest.approx(1.54332066, rel=1e-8)
    assert port_dP(990.0, v_port) == pytest.approx(1650.61419, rel=1e-8)


def test_closed_form_turbulent_branch() -> None:
    """Case 2: the Konakov branch at Re 3062.00293."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    v = channel_velocity(8.0, 990.0, geom.A_channel_m2, geom.channels_per_fluid)
    assert v == pytest.approx(1.07744108, rel=1e-8)
    Re = channel_Re(990.0, v, geom.D_h_m, 6.0e-4)
    assert Re == pytest.approx(3062.00293, rel=1e-8)
    f = friction_martin_vdi(Re, 45.0)
    assert f == pytest.approx(0.857073074, rel=1e-8)
    Nu = nusselt_martin_vdi(Re, 4180.0 * 6.0e-4 / 0.63, 45.0, f)
    assert Nu == pytest.approx(73.9326645, rel=1e-8)
    assert Nu * 0.63 / geom.D_h_m == pytest.approx(27042.6208, rel=1e-8)


@pytest.mark.parametrize(
    ("re", "angle", "expected"),
    [
        (500.0, 45.0, 1.06688451),
        (500.0, 60.0, 2.3862954),
        (2500.0, 45.0, 0.867587711),
        (2500.0, 60.0, 1.94223808),
    ],
)
def test_friction_spot_values(re: float, angle: float, expected: float) -> None:
    """Case 3: the explicit VDI form matches the spec's four spot values."""
    assert friction_martin_vdi(re, angle) == pytest.approx(expected, rel=1e-8)


def test_overall_u() -> None:
    """Case 4: U with both films at 13180.3884 W/m2K, 0.6 mm plate, k 16."""
    u = overall_u(
        h_hot=13180.3884,
        h_cold=13180.3884,
        t_plate_m=6.0e-4,
        k_plate=16.0,
        R_f_hot=0.0,
        R_f_cold=0.0,
    )
    assert u == pytest.approx(5284.2784, rel=1e-8)


def test_kumar_switch_runs() -> None:
    """The kumar switch routes friction and Nusselt to the book correlation.

    The pinned values are the library's own outputs at Re 1000, Pr 3.98095238
    (the spec's case-1 water), 45 degrees: they pin the wiring so a silent
    correlation swap fails the test.
    """
    assert friction_kumar(1000.0, 45.0) == pytest.approx(1.3890694890949535, rel=1e-12)
    assert nusselt_kumar(1000.0, 4180.0 * 6.0e-4 / 0.63, 45.0) == pytest.approx(46.14418278403326, rel=1e-12)
    assert friction_martin_vdi(1000.0, 45.0) != friction_kumar(1000.0, 45.0)


def test_missing_param_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="amplitude_m"):
        plate_geometry({k: v for k, v in GEOMETRY_P1.items() if k != "amplitude_m"})


def test_nonpositive_geometry_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="plate_width_m"):
        plate_geometry({**GEOMETRY_P1, "plate_width_m": 0.0})


def test_too_few_plates_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="n_plates"):
        plate_geometry({**GEOMETRY_P1, "n_plates": 2})


def test_chevron_angle_out_of_range_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="chevron_angle_deg"):
        plate_geometry({**GEOMETRY_P1, "chevron_angle_deg": 85.0})


def test_chevron_angle_zero_refuses() -> None:
    """phi = 0 degenerates Martin's Nusselt (sin 2phi = 0): refused, not a crash."""
    with pytest.raises(PlateGeometryError, match="chevron_angle_deg"):
        plate_geometry({**GEOMETRY_P1, "chevron_angle_deg": 0.0})
    with pytest.raises(PlateGeometryError, match="chevron_angle_deg"):
        plate_geometry({**GEOMETRY_P1, "chevron_angle_deg": 10.0})


def test_bad_correlation_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="correlation"):
        plate_geometry({**GEOMETRY_P1, "correlation": "taborek"})


def _thermo(pid: str) -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", pid)
    return impl


def _inlets(thermo: Thermo, **over: Any) -> dict[str, StreamState]:
    feeds, _ = PlateExchangerR1.example_case()
    feeds = {port: {**f, **over.get(port, {})} for port, f in feeds.items()}
    return {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for port, f in feeds.items()
    }


def _solve(thermo: Thermo, params: dict[str, Any], **feed_over: Any) -> Any:
    return PlateExchangerR1().solve(_inlets(thermo, **feed_over), params, thermo)


def test_example_case_solves_and_info_keys() -> None:
    """The example case rates on the default package with the spec's info keys."""
    thermo = _thermo("pr")
    result = _solve(thermo, dict(GEOMETRY_P1))
    for key in (
        "duty_W",
        "U_W_m2K",
        "A_m2",
        "UA_W_K",
        "NTU",
        "effectiveness",
        "LMTD_K",
        "h_hot_W_m2K",
        "h_cold_W_m2K",
        "Re_hot",
        "Re_cold",
        "dP_hot_Pa",
        "dP_cold_Pa",
        "correlation_in_range",
    ):
        assert key in result.info
    assert float(result.info["correlation_in_range"]) == 1.0
    assert float(result.info["duty_W"]) > 0.0
    # R0 convention: the unit-level duty_W is the round-off residual.
    assert result.duty_W == pytest.approx(0.0, abs=1e-6 * float(result.info["duty_W"]))


def test_reduction_to_r0_identity() -> None:
    """R0 replay of the R1 duty reproduces the R1 outlets to 1e-10 relative.

    The R0 solve runs ``two_stream`` with ``TwoStreamSpec(duty_W=Q_R1)`` and
    R1's per-side pressure drops on the same inlets (spec identity, on
    ``pr-peneloux``).
    """
    thermo = _thermo("pr-peneloux")
    result = _solve(thermo, dict(GEOMETRY_P1))
    inlets = _inlets(thermo)
    r0 = two_stream(
        inlets["hot_in"],
        inlets["cold_in"],
        TwoStreamSpec(duty_W=float(result.info["duty_W"])),
        thermo,
        dP_hot=float(result.info["dP_hot_Pa"]),
        dP_cold=float(result.info["dP_cold_Pa"]),
    )
    hot1, cold1 = result.outlets["hot_out"], result.outlets["cold_out"]
    for a, b in (
        (hot1.T, r0.hot_out.T),
        (hot1.enthalpy, r0.hot_out.enthalpy),
        (cold1.T, r0.cold_out.T),
        (cold1.enthalpy, r0.cold_out.enthalpy),
    ):
        assert a == pytest.approx(b, rel=1e-10)


def test_zero_flow_refuses() -> None:
    thermo = _thermo("pr")
    with pytest.raises(RatingError, match="needs both streams flowing"):
        _solve(thermo, dict(GEOMETRY_P1), hot_in={"molar_flow": 0.0})


def test_temperature_cross_refuses() -> None:
    thermo = _thermo("pr")
    with pytest.raises(TemperatureCross, match="inlet temperatures"):
        _solve(thermo, dict(GEOMETRY_P1), hot_in={"T": 293.15})


def test_two_phase_inlet_refuses() -> None:
    """A two-phase hot inlet reaches SinglePhaseRequired, side named.

    Rich gas below its dew point (the expander suite's two-phase recipe): the
    phase check runs before the solve. ``_side_kind`` appends the side name.
    """
    thermo = _thermo("pr")
    feeds, _ = PlateExchangerR1.example_case()
    hot = thermo.flash_pt({"C1": 0.85, "C3": 0.10, "nC5": 0.05}, 240.0, 8.0e6, 100.0)
    assert len(hot.phases) == 2  # precondition: the feed really is two-phase
    cold_feed = feeds["cold_in"]
    cold = thermo.flash_pt(cold_feed["composition"], cold_feed["T"], cold_feed["P"], cold_feed["molar_flow"])
    with pytest.raises(SinglePhaseRequired, match="hot inlet"):
        PlateExchangerR1().solve({"hot_in": hot, "cold_in": cold}, dict(GEOMETRY_P1), thermo)


def test_property_unavailable_names_property_and_side() -> None:
    """A package without transport properties is refused: property and side named."""

    class _NoTransport:
        def __init__(self, real: Thermo) -> None:
            self._real = real

        def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
            props = self._real.phase_props(composition, T, P, kind)
            return props.model_copy(update={"viscosity": None})

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    thermo = _thermo("pr")
    inlets = _inlets(thermo)
    with pytest.raises(PropertyUnavailable, match="viscosity.*hot") as excinfo:
        PlateExchangerR1().solve(inlets, dict(GEOMETRY_P1), cast(Thermo, _NoTransport(thermo)))
    assert "hot side" in str(excinfo.value)


def test_convergence_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A brentq failure surfaces as RatingConvergenceError with the bracket."""

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("mocked brentq failure")

    _thermo("pr")
    monkeypatch.setattr("ngdesign.units.heat.rating.brentq", boom)
    with pytest.raises(RatingConvergenceError, match="did not converge"):
        _solve(_thermo("pr"), dict(GEOMETRY_P1))


def test_correlation_range_refuses() -> None:
    """Re outside [200, 1e4] refuses unless allow_extrapolation; then flags 0."""
    thermo = _thermo("pr")
    # 5 mol/s hot water: Re far below 200 on the hot side.
    with pytest.raises(PlateCorrelationRangeError, match="Re"):
        _solve(thermo, dict(GEOMETRY_P1), hot_in={"molar_flow": 5.0})
    result = _solve(thermo, {**GEOMETRY_P1, "allow_extrapolation": True}, hot_in={"molar_flow": 5.0})
    assert float(result.info["correlation_in_range"]) == 0.0
