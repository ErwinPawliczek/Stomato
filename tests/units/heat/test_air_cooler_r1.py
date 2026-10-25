"""Closed-form and refusal tests for air_cooler R1 (spec U-R2, issue #315).

Hand-computed from the spec's equations on the 4-row example geometry from
ht's ``AirCooledExchanger`` docstring (``AirCooledExchanger(tube_rows=4,
tube_passes=4, tubes_per_row=20, tube_length=3, tube_diameter=0.0254,
fin_thickness=0.000406, fin_density=1/0.002309, pitch_normal=0.06033,
pitch_parallel=0.05207, fin_height=0.0159, tube_thickness=0.0034,
corbels=True)``), air at rho 1.1584 kg/m3, cp 1007 J/(kg K), mu 1.84e-5
Pa s, k 0.0263 W/(m K), k_fin 205 W/(m K):

1. Air side, mdot 8 kg/s:
   - ``V_max = m/(A_min*rho) = 8/(1.7603093*1.1584) = 3.9232181 m/s``;
   - ``Re = rho*V_max*D_o/mu = 1.1584*3.9232181*0.0254/1.84e-5 = 6273.601``;
   - ``Pr = 1007*1.84e-5/0.0263 = 0.70451711``;
   - fin gap ``s = bare_length = 0.002309 - 0.000406 = 0.001903 m``, fin
     height ``l_f = (0.0572 - 0.0254)/2 = 0.0159 m``;
     ``Nu = 0.134*6273.601^0.681*0.70451711^(1/3)*(0.001903/0.0159)^0.2*
     (0.001903/0.000406)^0.1134 = 35.8262065``;
   - ``h_fin = 35.8262065*0.0263/0.0254 = 37.095639 W/(m2 K)``;
   - ``eta_f`` (Kern-Kraus) = 0.899561982;
   - total-area basis ``h = (eta_f*A_fin + A_tube_showing)/A*h_fin =
     33.499866 W/(m2 K)``; bare basis ``h_bare = h*A_increase = 791.049477``.
2. ESDU 86022: ``K_f = 4.567*6273.601^-0.242*23.613512^0.504*
   (0.06033/0.0254)^-0.376*(0.05207/0.0254)^-0.546 = 1.32197789``;
   ``K_a = 1 + 0.47443918^2 = 1.22509253``;
   ``dP_air = (1.22509253 + 4*1.32197789)*1.1584*3.9232181^2/2 = 58.0623768 Pa``;
   fan power at eta 0.7: ``(8/1.1584)*58.0623768/0.7 = 572.833235 W``.
3. Range: mdot 30 kg/s gives ``Re = 6273.601*30/8 = 23526.0038`` - refused
   without ``allow_extrapolation``; with it ``h_bare = 1713.45968`` and
   ``dP_air = 635.02632 Pa`` (the same equations at the higher Re).

Every expected value is fixed BEFORE the run (spec U-R1 rule) at the 8-digit
rounding above; the assertions use rel=1e-8.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fluids.geometry import AirCooledExchanger

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.air_cooler_r1 import (
    AirCoolerGeometryError,
    AirCoolerR1,
    BriggsYoungRangeError,
    air_side_h,
    build_geometry,
    check_briggs_young_range,
    esdu_dP,
    fan_power_W,
)
from ngdesign.units.heat.rating import (
    PropertyUnavailable,
    RatingConvergenceError,
    SinglePhaseRequired,
)
from ngdesign.units.heat_exchange import HeatExchanger

#: The spec's closed-form geometry (ht docstring example), corbels=True.
GEO = AirCooledExchanger(
    tube_rows=4,
    tube_passes=4,
    tubes_per_row=20,
    tube_length=3.0,
    tube_diameter=0.0254,
    fin_thickness=0.000406,
    fin_density=1 / 0.002309,
    pitch_normal=0.06033,
    pitch_parallel=0.05207,
    fin_height=0.0159,
    tube_thickness=0.0034,
    corbels=True,
)

#: Air-side film properties of the closed-form case.
RHO, CP, MU, K_AIR, K_FIN = 1.1584, 1007.0, 1.84e-5, 0.0263, 205.0

#: Builder params mirroring the same bundle (the builder's params table has no
#: corbels entry, so area round-trips are checked against corbels=False).
BASE: dict[str, Any] = {
    "tube_rows": 4,
    "tube_passes": 4,
    "tubes_per_row": 20,
    "tube_length_m": 3.0,
    "tube_OD_m": 0.0254,
    "tube_wall_m": 0.0034,
    "fin_thickness_m": 0.000406,
    "fin_height_m": 0.0159,
    "fin_density_per_m": 1 / 0.002309,
    "pitch_parallel_m": 0.05207,
    "pitch_normal_m": 0.06033,
    "air_T_K": 308.15,
    "air_mass_flow_kg_s": 8.0,
    "fan_efficiency": 0.7,
}


def test_closed_form_air_side() -> None:
    """Test 1: V_max, Re, Pr, Nu, h_fin, eta_f, total-area h, bare h (rel 1e-8)."""
    r = air_side_h(8.0, GEO, 0.0254, RHO, CP, MU, K_AIR, K_FIN)
    assert r.V_max_m_s == pytest.approx(3.9232181, rel=1e-8)
    assert r.Re == pytest.approx(6273.601, rel=1e-8)
    assert r.Pr == pytest.approx(0.70451711, rel=1e-8)
    assert r.Nu == pytest.approx(35.8262065, rel=1e-8)
    assert r.h_fin_W_m2K == pytest.approx(37.095639, rel=1e-8)
    assert r.fin_efficiency == pytest.approx(0.899561982, rel=1e-8)
    assert r.h_total_W_m2K == pytest.approx(33.499866, rel=1e-8)
    assert r.h_bare_W_m2K == pytest.approx(791.049477, rel=1e-8)


def test_closed_form_esdu_dP_and_fan() -> None:
    """Test 2: K_f, K_a, dP_air, fan power at eta 0.7 (rel 1e-8)."""
    r = esdu_dP(8.0, GEO, 0.0254, 4, RHO, MU)
    assert r.K_f == pytest.approx(1.32197789, rel=1e-8)
    assert r.K_a == pytest.approx(1.22509253, rel=1e-8)
    assert r.dP_air_Pa == pytest.approx(58.0623768, rel=1e-8)
    assert fan_power_W(8.0, RHO, r.dP_air_Pa, 0.7) == pytest.approx(572.833235, rel=1e-8)


def test_briggs_young_range_check() -> None:
    """Test 3: Re 23526.0038 refuses without allow_extrapolation, passes with it."""
    assert check_briggs_young_range(6273.601, allow_extrapolation=False) is True
    with pytest.raises(BriggsYoungRangeError, match="Re_air"):
        check_briggs_young_range(23526.0038, allow_extrapolation=False)
    assert check_briggs_young_range(23526.0038, allow_extrapolation=True) is False
    # The extrapolated numbers of the spec's test 3 (same equations, mdot 30).
    r = air_side_h(30.0, GEO, 0.0254, RHO, CP, MU, K_AIR, K_FIN)
    assert r.Re == pytest.approx(23526.0038, rel=1e-8)
    assert r.h_bare_W_m2K == pytest.approx(1713.45968, rel=1e-8)
    dP = esdu_dP(30.0, GEO, 0.0254, 4, RHO, MU)
    assert dP.dP_air_Pa == pytest.approx(635.02632, rel=1e-8)


def test_builder_round_trips_the_docstring_geometry() -> None:
    """build_geometry reproduces the docstring bundle's areas from params."""
    v = build_geometry(BASE)
    plain = AirCooledExchanger(
        tube_rows=4,
        tube_passes=4,
        tubes_per_row=20,
        tube_length=3.0,
        tube_diameter=0.0254,
        fin_thickness=0.000406,
        fin_density=1 / 0.002309,
        pitch_normal=0.06033,
        pitch_parallel=0.05207,
        fin_height=0.0159,
        tube_thickness=0.0034,
    )
    assert v.geo.A == pytest.approx(plain.A, rel=1e-12)
    assert v.geo.A_min == pytest.approx(plain.A_min, rel=1e-12)
    assert v.geo.A_increase == pytest.approx(plain.A_increase, rel=1e-12)
    assert v.geo.A_bare_tube == pytest.approx(plain.A_bare_tube, rel=1e-12)
    assert v.geo.A_tube_flow == pytest.approx(plain.A_tube_flow, rel=1e-12)
    assert v.tube_rows == 4 and v.tube_passes == 4 and v.tubes_per_row == 20
    assert v.passes_equal_rows_over_four is False
    assert v.k_fin_W_mK == 205.0 and v.k_wall_W_mK == 45.0
    assert v.R_f_tube_m2K_W == 0.0 and v.roughness_m == 4.5e-5
    assert v.air_P_Pa == 101325.0
    assert v.air_composition == {"N2": 0.79, "O2": 0.21}
    assert v.allow_extrapolation is False


def test_builder_accepts_alternative_param_spellings() -> None:
    """fin_diameter_m + fin_interval_m and pitch_m + angle_deg build the same bundle."""
    params = {
        k: v
        for k, v in BASE.items()
        if k not in ("fin_height_m", "fin_density_per_m", "pitch_parallel_m", "pitch_normal_m")
    }
    v = build_geometry(
        {
            **params,
            "fin_diameter_m": 0.0254 + 2 * 0.0159,
            "fin_interval_m": 0.002309,
            "pitch_m": 0.056,
            "angle_deg": 30.0,
        }
    )
    fin_diameter = v.geo.fin_diameter
    assert fin_diameter is not None
    assert fin_diameter == pytest.approx(GEO.fin_diameter, rel=1e-12)
    assert v.geo.bare_length == pytest.approx(GEO.bare_length, rel=1e-12)


def test_builder_flags_passes_rows_over_four() -> None:
    """(5, 5) runs on ht's passes = rows assumption and is flagged, not refused."""
    v = build_geometry({**BASE, "tube_rows": 5, "tube_passes": 5})
    assert v.passes_equal_rows_over_four is True


def test_missing_param_refuses() -> None:
    for name in (
        "tube_rows",
        "tube_passes",
        "tubes_per_row",
        "tube_length_m",
        "tube_OD_m",
        "tube_wall_m",
        "fin_thickness_m",
        "air_T_K",
        "air_mass_flow_kg_s",
        "fan_efficiency",
    ):
        params = {k: v for k, v in BASE.items() if k != name}
        with pytest.raises(AirCoolerGeometryError, match=name):
            build_geometry(params)


def test_nonpositive_param_refuses() -> None:
    for name in ("tube_length_m", "tube_OD_m", "tube_wall_m", "fin_thickness_m", "air_T_K"):
        with pytest.raises(AirCoolerGeometryError, match=name):
            build_geometry({**BASE, name: 0.0})


def test_both_fin_size_alternatives_refuse() -> None:
    with pytest.raises(AirCoolerGeometryError, match="fin_height_m/fin_diameter_m"):
        build_geometry({**BASE, "fin_diameter_m": 0.0572})


def test_no_fin_size_alternative_refuses() -> None:
    params = {k: v for k, v in BASE.items() if k != "fin_height_m"}
    with pytest.raises(AirCoolerGeometryError, match="fin_height_m/fin_diameter_m"):
        build_geometry(params)


def test_both_fin_spacing_alternatives_refuse() -> None:
    with pytest.raises(AirCoolerGeometryError, match="fin_density_per_m/fin_interval_m"):
        build_geometry({**BASE, "fin_interval_m": 0.002309})


def test_unsupported_passes_rows_pair_refuses() -> None:
    with pytest.raises(AirCoolerGeometryError, match="tube_passes/tube_rows"):
        build_geometry({**BASE, "tube_rows": 4, "tube_passes": 3})


def test_both_pitch_pairs_refuse() -> None:
    with pytest.raises(AirCoolerGeometryError, match="one pitch pair"):
        build_geometry({**BASE, "pitch_m": 0.056, "angle_deg": 30.0})


def test_pitch_without_angle_refuses() -> None:
    params = {k: v for k, v in BASE.items() if k != "pitch_parallel_m"}
    with pytest.raises(AirCoolerGeometryError, match="angle_deg"):
        build_geometry({**params, "pitch_m": 0.056})


def test_no_pitch_refuses() -> None:
    params = {k: v for k, v in BASE.items() if k not in ("pitch_parallel_m", "pitch_normal_m")}
    with pytest.raises(AirCoolerGeometryError, match="pitch"):
        build_geometry(params)


def test_zero_air_flow_refuses() -> None:
    with pytest.raises(AirCoolerGeometryError, match="air_mass_flow_kg_s"):
        build_geometry({**BASE, "air_mass_flow_kg_s": 0.0})


def test_bad_fan_efficiency_refuses() -> None:
    for bad in (0.0, -0.5, 1.001, 1.5):
        with pytest.raises(AirCoolerGeometryError, match="fan_efficiency"):
            build_geometry({**BASE, "fan_efficiency": bad})
    assert build_geometry({**BASE, "fan_efficiency": 1.0}).fan_efficiency == 1.0


def test_bad_air_composition_refuses() -> None:
    with pytest.raises(AirCoolerGeometryError, match="air_composition"):
        build_geometry({**BASE, "air_composition": {"N2": 0.5, "O2": 0.4}})



def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _inlet(thermo: Thermo, **over: Any) -> Any:
    feeds, _ = AirCoolerR1.example_case()
    feed = {**feeds["inlet"], **over}
    return thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


def _solve(thermo: Thermo, params: dict[str, Any] | None = None, **feed_over: Any) -> Any:
    _, base_params = AirCoolerR1.example_case()
    return AirCoolerR1().solve(
        {"inlet": _inlet(thermo, **feed_over)}, params if params is not None else base_params, thermo
    )


def test_example_case_rates_with_spec_info_keys() -> None:
    """The E-101 basis rates; duty convention, info keys and sanity ranges hold."""
    thermo = _thermo()
    result = _solve(thermo)
    assert result.power_W == 0.0
    assert float(result.duty_W) < 0.0  # cooling: the R0 duty convention
    q = float(result.info["Q_W"])
    assert q > 0.0
    assert q == pytest.approx(-float(result.duty_W), rel=1e-6)
    for key in (
        "Q_W",
        "U_bare_W_m2K",
        "A_bare_m2",
        "A_total_m2",
        "F_t",
        "LMTD_K",
        "h_air_bare_W_m2K",
        "fin_efficiency",
        "Re_air",
        "h_tube_W_m2K",
        "Re_tube",
        "dP_tube_Pa",
        "dP_air_Pa",
        "fan_power_W",
        "air_T_out_K",
        "briggs_young_in_range",
        "passes_equal_rows_assumption",
    ):
        assert key in result.info
    assert float(result.info["briggs_young_in_range"]) == 1.0
    assert float(result.info["passes_equal_rows_assumption"]) == 0.0
    assert 308.15 < float(result.info["air_T_out_K"]) < 322.15
    assert 1000.0 < float(result.info["Re_air"]) < 8000.0
    assert float(result.info["LMTD_K"]) > 0.0
    assert 0.0 < float(result.info["F_t"]) <= 1.0
    assert float(result.info["dP_air_Pa"]) > 0.0 and float(result.info["dP_tube_Pa"]) > 0.0
    assert float(result.info["fan_power_W"]) > 0.0


def test_reduction_to_r0_identity() -> None:
    """R0 with R1's duty and tube dP reproduces R1's outlet to 1e-10 relative."""
    thermo = _thermo()
    result = _solve(thermo)
    inlet = _inlet(thermo)
    r0 = HeatExchanger().solve(
        {"inlet": inlet},
        {"duty_W": float(result.duty_W), "dP": float(result.info["dP_tube_Pa"])},
        thermo,
    )
    r1_out = result.outlets["outlet"]
    assert r1_out.T == pytest.approx(r0.outlets["outlet"].T, rel=1e-10)
    assert r1_out.enthalpy == pytest.approx(r0.outlets["outlet"].enthalpy, rel=1e-10)


def test_process_inlet_below_air_refuses() -> None:
    """A process inlet at or below the air inlet temperature is a cross."""
    with pytest.raises(TemperatureCross, match="air inlet"):
        _solve(_thermo(), T=305.0)


def test_two_phase_inlet_refuses() -> None:
    """A two-phase inlet reaches SinglePhaseRequired (the phase check first)."""
    thermo = _thermo()
    two_phase = thermo.flash_pt({"C1": 0.85, "C3": 0.10, "nC5": 0.05}, 240.0, 8.0e6, 100.0)
    assert len(two_phase.phases) == 2  # precondition: the feed really is two-phase
    _, params = AirCoolerR1.example_case()
    with pytest.raises(SinglePhaseRequired, match="R1 rates single-phase duty"):
        AirCoolerR1().solve({"inlet": two_phase}, params, thermo)


def test_property_unavailable_names_the_side() -> None:
    """A thermo package without transport properties is refused."""

    class _NoTransport:
        def __init__(self, real: Thermo) -> None:
            self._real = real

        def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
            props = self._real.phase_props(composition, T, P, kind)
            return props.model_copy(update={"viscosity": None})

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    thermo = _thermo()
    inlets = {"inlet": _inlet(thermo)}
    _, params = AirCoolerR1.example_case()
    with pytest.raises(PropertyUnavailable):
        AirCoolerR1().solve(inlets, params, cast(Thermo, _NoTransport(thermo)))


def test_convergence_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A brentq failure surfaces as RatingConvergenceError with the bracket."""

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("mocked brentq failure")

    _thermo()
    monkeypatch.setattr("ngdesign.units.heat.air_cooler_r1.brentq", boom)
    with pytest.raises(RatingConvergenceError, match="rating did not converge"):
        _solve(_thermo())


def test_re_range_refusal_and_extrapolation_flag() -> None:
    """30 kg/s air leaves the Briggs-Young window: refused, then flagged."""
    thermo = _thermo()
    with pytest.raises(BriggsYoungRangeError, match="Re_air"):
        _solve(thermo, air_mass_flow_kg_s=30.0)
    _, params = AirCoolerR1.example_case()
    extrap = _solve(thermo, {**params, "allow_extrapolation": True}, air_mass_flow_kg_s=30.0)
    assert float(extrap.info["briggs_young_in_range"]) == 0.0
