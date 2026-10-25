"""Closed-form Kern-method tests for shell_tube R1 (spec: Tests 1-3).

Hand-checkable chain from the spec's equations on geometry G1
(D_s 0.489 m; 158 tubes, 19.05/14.83 mm; L 4.877 m; P_T 23.81 mm
triangular; B 0.3048 m; 15 baffles; 2 passes), with the expected values
independent numbers transcribed from the spec:

1. Shell (Kern): mdot 18 kg/s, rho 995, mu 8.0e-4, k 0.615, cp 4180.
   - a_s = Ds*(PT-Do)*B/PT = 0.489*0.00476*0.3048/0.02381 = 0.0297969203 m2
   - De,tri = 4*(sqrt(3)/4*PT^2 - pi*Do^2/8)/(pi*Do/2) = 0.0137644071 m
   - De,sq = 4*(PT^2 - pi*Do^2/4)/(pi*Do) = 0.0188408135 m
   - G_s = 18/0.0297969203 = 604.089276 kg/(m2 s); Re_s = De*Gs/mu = 10393.6634
   - Pr = cp*mu/k = 4180*8e-4/0.615 = 5.43739837
   - h_o = 0.36*(0.615/0.0137644071)*10393.6634^0.55*5.43739837^(1/3)
     = 4579.02747 W/(m2 K)
   - f = exp(0.576 - 0.19*ln(10393.6634)) = 0.306879289
   - dP_s = f*Gs^2*(15+1)*Ds/(2*995*De) = 31988.0737 Pa
2. Tube: mdot 12 kg/s, rho 700, mu 4.0e-4, k 0.12, cp 2300, eps 4.5e-5.
   - A/pass = (158/2)*pi*0.01483^2/4 = 0.0136458086 m2
   - v = 12/(700*0.0136458086) = 1.25627273 m/s; Re = rho*v*Di/mu = 32603.4179
   - Colebrook at e/D = 4.5e-5/0.01483: f_D = 0.0297781346
   - Gnielinski: Nu = 278.547286, h_i = Nu*k/Di = 2253.92274 W/(m2 K)
   - dP_t = 2*f_D*(L/Di)*rho*v^2/2 + 4*2*rho*v^2/2 = 15237.7172 Pa
3. U and area: U_o clean (k_w 45) = 1188.61873 W/(m2 K);
   A_o = 158*pi*0.01905*4.877 = 46.1163254 m2; UA = 54814.7284 W/K.

All assertions use rel 1e-8 (the spec's closed-form band; the expected
values are quoted to 9-10 significant figures).
"""

from __future__ import annotations

import math
from typing import Any

import ht
import pytest

from ngdesign import registry
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import FilmProps, RatingError, SinglePhaseRequired, u_outside_tube
from ngdesign.units.heat.shell_tube_r1 import (
    KernRangeError,
    ShellTubeGeometryError,
    ShellTubeR1,
    eps_counterflow,
    eps_tema_e,
    equiv_diameter,
    shell_dP,
    shell_flow_area,
    shell_friction,
    shell_h,
    tube_dP,
    tube_duct,
    tube_flow_area,
)
from ngdesign.units.heat_exchange import HeatExchanger

#: Geometry G1 from the spec's Tests section.
DS = 0.489
N_TUBES = 158
TUBE_OD = 0.01905
TUBE_ID = 0.01483
LENGTH = 4.877
PITCH = 0.02381
BAFFLE = 0.3048
N_BAFFLES = 15
N_PASSES = 2

REL = 1e-8


def _rel(got: float, want: float) -> float:
    return abs(got - want) / abs(want)


def test_shell_side_kern_chain() -> None:
    """Eq. S1-S3 shell chain: a_s, De per layout, Gs, Re_s, Pr, h_o, f, dP_s."""
    a_s = shell_flow_area(DS, PITCH, TUBE_OD, BAFFLE)
    assert _rel(a_s, 0.0297969203) < REL
    de_tri = equiv_diameter(PITCH, TUBE_OD, "triangular30")
    de_sq = equiv_diameter(PITCH, TUBE_OD, "square90")
    assert _rel(de_tri, 0.0137644071) < REL
    assert _rel(de_sq, 0.0188408135) < REL
    gs = 18.0 / a_s
    assert _rel(gs, 604.089276) < REL
    re_s = de_tri * gs / 8.0e-4
    assert _rel(re_s, 10393.6634) < REL
    pr = 4180.0 * 8.0e-4 / 0.615
    assert _rel(pr, 5.43739837) < REL
    h_o = shell_h(0.615, de_tri, re_s, pr)
    assert _rel(h_o, 4579.02747) < REL
    f = shell_friction(re_s)
    assert _rel(f, 0.306879289) < REL
    dP_s = shell_dP(f, gs, N_BAFFLES, DS, 995.0, de_tri)
    assert _rel(dP_s, 31988.0737) < REL


def test_tube_side_kern_chain() -> None:
    """Tube chain: area per pass, v, Re, Colebrook f_D, Gnielinski h_i, dP with returns."""
    area = tube_flow_area(N_TUBES, N_PASSES, TUBE_ID)
    assert _rel(area, 0.0136458086) < REL
    props = FilmProps(rho_kg_m3=700.0, mu_Pa_s=4.0e-4, k_W_mK=0.12, cp_J_kgK=2300.0)
    duct = tube_duct(12.0, N_TUBES, N_PASSES, TUBE_ID, props, 4.5e-5)
    assert _rel(duct.v_m_s, 1.25627273) < REL
    assert _rel(duct.Re, 32603.4179) < REL
    assert _rel(duct.fd, 0.0297781346) < REL
    assert _rel(duct.h_W_m2K, 2253.92274) < REL
    dP = tube_dP(duct.fd, N_PASSES, LENGTH, TUBE_ID, 700.0, duct.v_m_s)
    assert _rel(dP, 15237.7172) < REL


def test_u_and_area() -> None:
    """Clean overall U on the outside area and A_o = Nt*pi*Do*L."""
    props = FilmProps(rho_kg_m3=700.0, mu_Pa_s=4.0e-4, k_W_mK=0.12, cp_J_kgK=2300.0)
    duct = tube_duct(12.0, N_TUBES, N_PASSES, TUBE_ID, props, 4.5e-5)
    h_o = shell_h(0.615, 0.0137644071, 10393.6634, 5.43739837)
    u_o = u_outside_tube(h_i=duct.h_W_m2K, h_o=h_o, Do=TUBE_OD, Di=TUBE_ID, k_wall=45.0, R_fi=0.0, R_fo=0.0)
    assert _rel(u_o, 1188.61873) < REL
    a_o = N_TUBES * math.pi * TUBE_OD * LENGTH
    assert _rel(a_o, 46.1163254) < REL
    assert _rel(u_o * a_o, 54814.7284) < REL


def test_shell_friction_below_fit_band_refuses() -> None:
    """The S3 fit is valid for 400 < Re_s <= 1e6; outside it the fit refuses."""
    with pytest.raises(KernRangeError, match="Re_s"):
        shell_friction(399.0)
    with pytest.raises(KernRangeError, match="Re_s"):
        shell_friction(1.0e7)
    # The band edges themselves are exact equality checks, not tolerance checks.
    assert shell_friction(400.0 * (1.0 + 1e-12)) == pytest.approx(
        math.exp(0.576 - 0.19 * math.log(400.0 * (1.0 + 1e-12)))
    )


# --- R1 adapter tests (spec Tests 4-6, identity and refusal rows) ------------

EPS_REL = 1e-8


def _thermo() -> Any:
    registry.discover()
    impl: Any = registry.create("thermo", "pr")
    return impl


def _inlet(thermo: Any, **over: Any) -> tuple[Any, dict[str, Any]]:
    """The example case's process feed as a StreamState, plus the params."""
    feeds, params = ShellTubeR1.example_case()
    feed = {**feeds["inlet"], **over}
    state = thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
    return state, params


def test_effectiveness_tema_e_matches_spec_values() -> None:
    """Test 4: S&T effectiveness values transcribed from the spec (rel 1e-8)."""
    assert eps_tema_e(1.0, 0.5, 2, 1) == pytest.approx(0.539939556, rel=EPS_REL)
    assert eps_tema_e(1.0, 0.5, 2, 2) == pytest.approx(0.558304442, rel=EPS_REL)
    assert eps_tema_e(2.0, 0.8, 2, 1) == pytest.approx(0.606995080, rel=EPS_REL)
    assert eps_tema_e(2.0, 0.8, 2, 2) == pytest.approx(0.679833500, rel=EPS_REL)
    # Single tube pass in a single shell is pure counterflow (Incropera 11.29a/b).
    assert eps_tema_e(1.0, 0.5, 1, 1) == pytest.approx(eps_counterflow(1.0, 0.5), rel=EPS_REL)
    assert eps_counterflow(2.0, 0.8) == pytest.approx(
        (1.0 - math.exp(-2.0 * 0.2)) / (1.0 - 0.8 * math.exp(-0.4)), rel=EPS_REL
    )


def test_F_fakheri_matches_spec_value() -> None:
    """Test 5: Fakheri F for 450/370 K hot, 300/340 K cold, one shell (rel 1e-8)."""
    f = ht.F_LMTD_Fakheri(450.0, 370.0, 300.0, 340.0, shells=1)  # type: ignore[arg-type]  # ht 1.2.0 mis-annotates Thi/Tci as int
    assert f == pytest.approx(0.926902303, rel=EPS_REL)


def test_r0_replay_identity() -> None:
    """Test 6: the R0 HeatExchanger replay of the R1 duty gives the R1 outlet.

    HeatExchanger with duty_W = R1's process duty and dP = R1's process-side
    (tube) pressure drop runs the same flash_ph chain, so the outlet state
    must agree to 1e-10 relative.
    """
    thermo = _thermo()
    state, params = _inlet(thermo)
    result = ShellTubeR1().solve({"inlet": state}, params, thermo)
    outlet = result.outlets["outlet"]
    r0 = HeatExchanger().solve(
        {"inlet": state},
        {"duty_W": result.duty_W, "dP": state.P - outlet.P},
        thermo,
    )
    r0_out = r0.outlets["outlet"]
    assert outlet.T == pytest.approx(r0_out.T, rel=1e-10)
    assert outlet.enthalpy == pytest.approx(r0_out.enthalpy, rel=1e-10)


def test_missing_or_nonpositive_utility_params_refuse() -> None:
    """Each required utility param is refused by name when missing or <= 0."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    for drop in ("utility_composition", "utility_T_K", "utility_P_Pa", "utility_molar_flow"):
        broken = {k: v for k, v in params.items() if k != drop}
        with pytest.raises(ShellTubeGeometryError, match=drop):
            ShellTubeR1().solve({"inlet": state}, broken, thermo)
    with pytest.raises(ShellTubeGeometryError, match="utility_molar_flow"):
        ShellTubeR1().solve({"inlet": state}, {**params, "utility_molar_flow": 0.0}, thermo)


def test_equal_inlet_temperatures_refuse() -> None:
    """No driving force when the process and utility inlets are isothermal."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    with pytest.raises(TemperatureCross, match="no driving force"):
        ShellTubeR1().solve({"inlet": state}, {**params, "utility_T_K": 322.15}, thermo)


def test_two_phase_process_inlet_refuses_to_r2() -> None:
    """A two-phase feed (the slice gas WITH its free water at 315 K) points at R2."""
    thermo = _thermo()
    _, params = _inlet(thermo)
    wet = thermo.flash_pt(INLET_COMPOSITION, 315.0, 7.0e6, 50 * MMSCFD_TO_MOL_S)
    assert float(wet.vapor_fraction) < 1.0
    with pytest.raises(SinglePhaseRequired, match="use model R2"):
        ShellTubeR1().solve({"inlet": wet}, params, thermo)


def test_condensing_within_rating_refuses() -> None:
    """A vapor feed that condenses across the rating bracket refuses mid-solve.

    The R0 7 MPa dry gas is single-phase vapor at the inlet but its dew
    envelope covers the full-duty bracket end (303.15 K), so the shared core's
    Q_max evaluation raises SinglePhaseRequired before any iteration.
    """
    thermo = _thermo()
    _, params = _inlet(thermo)
    hot = thermo.flash_pt(INLET_COMPOSITION, 322.15, 7.0e6, 50 * MMSCFD_TO_MOL_S)
    with pytest.raises(SinglePhaseRequired, match="leaves the inlet's phase"):
        ShellTubeR1().solve({"inlet": hot}, params, thermo)


def test_kern_band_refusal_and_extrapolation_flag() -> None:
    """A starved utility leaves Kern's Re_s band; the flag waives it explicitly."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    starved = {**params, "utility_molar_flow": 100.0}
    with pytest.raises(KernRangeError, match="validity band"):
        ShellTubeR1().solve({"inlet": state}, starved, thermo)
    waived = ShellTubeR1().solve({"inlet": state}, {**starved, "allow_extrapolation": True}, thermo)
    assert float(waived.info["kern_in_range"]) == 0.0
    inband = ShellTubeR1().solve({"inlet": state}, params, thermo)
    assert float(inband.info["kern_in_range"]) == 1.0


def test_nonpositive_outlet_pressure_refuses() -> None:
    """The spec's refusal row: a dP larger than the inlet pressure refuses."""
    thermo = _thermo()
    state, params = _inlet(thermo, P=2.0e5)
    with pytest.raises(RatingError, match="non-positive outlet pressure"):
        ShellTubeR1().solve({"inlet": state}, params, thermo)


def test_info_keys_and_duty_convention() -> None:
    """The spec's info keys are present; the cooled process gives negative duty."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    result = ShellTubeR1().solve({"inlet": state}, params, thermo)
    for key in (
        "Q_W",
        "U_W_m2K",
        "A_m2",
        "UA_W_K",
        "NTU",
        "effectiveness",
        "F_LMTD",
        "LMTD_K",
        "h_tube_W_m2K",
        "h_shell_W_m2K",
        "Re_tube",
        "Re_shell",
        "dP_tube_Pa",
        "dP_shell_Pa",
        "utility_T_out_K",
        "utility_P_out_Pa",
        "utility_duty_W",
        "kern_in_range",
    ):
        assert key in result.info
    assert result.duty_W < 0.0
    outlet = result.outlets["outlet"]
    assert params["utility_T_K"] < outlet.T < state.T
    assert float(outlet.vapor_fraction) == pytest.approx(1.0)
    # The utility leaves hotter than it entered, below the process inlet.
    assert params["utility_T_K"] < float(result.info["utility_T_out_K"]) < state.T
