"""Closed-form tests for fired_heater R1 (specs/backend/units/fired_heater.md).

All expected numbers are hand-computed from the spec's equations, independent
of the implementation:

Test 1 (stoichiometry, methane, 15% excess, air 0.79/0.21): methane is CH4, so
C = 1, H = 4, O2_th = 1 + 4/4 = 2 mol/mol fuel. Air = (1 + 0.15)*2/0.21 =
2.3/0.21 = 10.95238095238... mol; air N2 = 0.79*that = 8.65238095238... mol.
Flue per mol fuel: CO2 1 + H2O 2 + O2 0.15*2 = 0.3 + N2 8.65238095238 = 11.95238095238
mol total, giving y_CO2 = 1/11.95238095238 = 0.08366533865, y_H2O = 2/... =
0.16733067729, y_O2 = 0.3/... = 0.02509960159, y_N2 = 8.65238095238/... =
0.72390438247.

Test 2 (Lobo-Evans): radiation = 5.670374419e-8 * 60 * 0.6 * (1100^4 - 650^4)
= 5.670374419e-8 * 36 * 1.28559375e12 = 2624327.25 W (exact product of the
typed decimals: 36 * 1.28559375e12 = 4.6281375e13; times 5.670374419e-8 =
2624327.2499...); convection = 11.36 * 200 * (1100 - 650) = 1022400.0 W
(exact); Q_R = 3646727.25 W; mean flux = 3646727.25/200 = 18233.63625 W/m2.

Test 3 (unit conversion): 2 Btu/(h ft2 degF) = 2 * 1055.05585262 J / (3600 s *
0.3048^2 m2 * 5/9 K) = 11.35652668... W/(m2 K); the module default constant
11.3565267 is that value rounded to 8 significant figures.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from scipy.optimize import brentq

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.heat.fired_heater import FiredHeater, fuel_lhv
from ngdesign.units.heat.fired_heater_r1 import (
    H_CONV_RADIANT_DEFAULT,
    FiredHeaterConvergenceError,
    FiredHeaterDewPointError,
    FiredHeaterR1,
    FiredHeaterSpecError,
    btu_h_ft2_f_to_w_m2_k,
    combustion_stoichiometry,
    mixture_enthalpy,
    radiant_transfer_W,
    solve_fuel_and_sections,
    validate_params,
)


def test_stoichiometry_methane_15pct_excess() -> None:
    """Hand-computed above (docstring): closed-form test 1, rel 1e-8."""
    result = combustion_stoichiometry({"C1": 1.0}, {"N2": 0.79, "O2": 0.21}, excess_air_frac=0.15)
    assert result["O2_th"] == pytest.approx(2.0, rel=1e-12)
    assert result["nu_air"] == pytest.approx(10.95238095238095, rel=1e-8)
    assert result["nu_fg"] == pytest.approx(11.95238095238095, rel=1e-8)
    flue: dict[str, float] = result["flue"]
    total = sum(flue.values())
    assert total == pytest.approx(result["nu_fg"], rel=1e-12)
    assert flue["CO2"] == pytest.approx(1.0, rel=1e-12)
    assert flue["H2O"] == pytest.approx(2.0, rel=1e-12)
    assert flue["O2"] == pytest.approx(0.3, rel=1e-12)
    assert flue["N2"] == pytest.approx(8.65238095238095, rel=1e-8)
    for species, expected_y in (
        ("CO2", 0.08366533865),
        ("H2O", 0.16733067729),
        ("O2", 0.02509960159),
        ("N2", 0.72390438247),
    ):
        assert flue[species] / total == pytest.approx(expected_y, rel=1e-8)


def test_lobo_evans_radiant_transfer() -> None:
    """Hand-computed above (docstring): closed-form test 2, rel 1e-9."""
    q_radiation, q_convection = radiant_transfer_W(
        alpha_Acp_m2=60.0,
        exchange_factor=0.6,
        T_g=1100.0,
        T_t=650.0,
        tube_area_m2=200.0,
        h_conv=11.36,
    )
    assert q_radiation == pytest.approx(2624327.25, rel=1e-9)
    assert q_convection == pytest.approx(1022400.0, rel=1e-9)
    q_total = q_radiation + q_convection
    assert q_total == pytest.approx(3646727.25, rel=1e-9)
    assert q_total / 200.0 == pytest.approx(18233.63625, rel=1e-9)


def test_btu_conversion_is_the_h_conv_default() -> None:
    """Hand-computed above (docstring): closed-form test 3; the default h_c is
    the Lobo-Evans 2 Btu/(h ft2 degF)."""
    converted = btu_h_ft2_f_to_w_m2_k(2.0)
    assert converted == pytest.approx(11.3565267, rel=1e-7)
    assert H_CONV_RADIANT_DEFAULT == pytest.approx(converted, rel=1e-7)


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _base_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "T_out": 600.0,
        "dP": 1.0e4,
        "fuel_composition": {"C1": 1.0},
        "excess_air_frac": 0.15,
        "alpha_Acp_m2": 60.0,
        "exchange_factor": 0.6,
        "tube_area_radiant_m2": 200.0,
        "tube_wall_excess_K": 100.0,
        "UA_convection_W_K": 300.0,
    }
    params.update(overrides)
    return params


def test_fuel_composition_required_at_r1() -> None:
    params = _base_params()
    del params["fuel_composition"]
    with pytest.raises(FiredHeaterSpecError, match="fuel_composition"):
        validate_params(params)


@pytest.mark.parametrize(
    "name", ["alpha_Acp_m2", "exchange_factor", "tube_area_radiant_m2", "UA_convection_W_K"]
)
def test_geometry_params_required_and_positive(name: str) -> None:
    for bad in (None, 0.0, -1.0):
        params = _base_params()
        if bad is None:
            del params[name]
        else:
            params[name] = bad
        with pytest.raises(FiredHeaterSpecError, match=name):
            validate_params(params)


def test_exchange_factor_above_one_refused() -> None:
    with pytest.raises(FiredHeaterSpecError, match="exchange_factor"):
        validate_params(_base_params(exchange_factor=1.01))


def test_negative_excess_air_refused() -> None:
    with pytest.raises(FiredHeaterSpecError, match="excess_air_frac"):
        validate_params(_base_params(excess_air_frac=-0.01))


@pytest.mark.parametrize("bad", [-0.01, 0.5])
def test_radiant_loss_frac_out_of_band_refused(bad: float) -> None:
    with pytest.raises(FiredHeaterSpecError, match="radiant_loss_frac"):
        validate_params(_base_params(radiant_loss_frac=bad))


# ---------------------------------------------------------------------------
# Spec algorithm 3: the coupled fuel / bridgewall / stack solves
# ---------------------------------------------------------------------------

_EXAMPLE_GEOMETRY = {
    "alpha_Acp_m2": 8.0,
    "exchange_factor": 0.6,
    "tube_area_m2": 200.0,
    "UA_convection_W_K": 1200.0,
}


def _example_basis(**overrides: Any) -> tuple[Thermo, dict[str, Any]]:
    """The spec identity example: methane fuel heating natural gas 300 -> 600 K.

    Measured on the vapour-phase reference (review round on e7c2531, item 1)
    with this geometry (alpha_Acp 8 m2, F 0.6, A_t 200 m2, UA_C 1200 W/K):
    efficiency_LHV 0.9366, Q = 1,317,508.1 W, T_g 941.4 K, T_stack 435.4 K,
    T_ad 2126.9 K. (The earlier 0.8253/936.5/463.3/1964.8 figures were read on
    a condensing flash_pt reference, which hid about 9.8 % of the fired heat in
    the flue water latent heat.)
    """
    thermo = _thermo()
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e5, 100.0)
    out = thermo.flash_pt({"C1": 1.0}, 600.0, 4.9e5, 100.0)
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.15)
    basis: dict[str, Any] = {
        "lhv_J_per_mol": fuel_lhv({"C1": 1.0}),
        "flue_mol": stoich["flue"],
        "air_fractions": {"N2": 0.79, "O2": 0.21},
        "nu_air": stoich["nu_air"],
        "nu_fg": stoich["nu_fg"],
        "Q_W": 100.0 * (out.enthalpy - inlet.enthalpy),
        "F_mol_s": 100.0,
        "h_in_J_per_mol": inlet.enthalpy,
        "T_in_K": inlet.T,
        "T_out_K": out.T,
        "P_out_Pa": 4.9e5,
        "composition": {"C1": 1.0},
        "air_T_K": 298.15,
        "box_P_Pa": 101325.0,
        "tube_wall_excess_K": 100.0,
        "h_conv_W_m2K": 11.3565267,
        "radiant_loss_frac": 0.0,
    }
    basis.update(_EXAMPLE_GEOMETRY)
    basis.update(overrides)
    return thermo, basis


def test_fuel_and_sections_self_consistent() -> None:
    """Hand-computed basis (docstring of _example_basis): the solve closes
    Eqs. 2-4 mutually. Independent re-evaluation here: Eq. 2 at the reported
    bridgewall (firebox balance, rel 1e-8), the Eq. 4 residual (UA*LMTD - Q_C,
    rel 1e-8 of Q), the duty split, and the temperature ordering."""
    thermo, basis = _example_basis()
    result = solve_fuel_and_sections(thermo, **basis)
    Q = basis["Q_W"]
    assert abs(result["residual_W"]) < 1e-8 * Q
    assert result["Q_radiant_W"] + result["Q_convection_W"] == pytest.approx(Q, rel=1e-12)
    assert 0.20 < result["efficiency_LHV"] < 1.0
    assert basis["T_in_K"] < result["T_crossover_K"] < basis["T_out_K"]
    assert 298.15 < result["T_stack_K"] < result["T_bridgewall_K"] < result["T_adiabatic_K"]
    assert basis["T_in_K"] < result["T_tube_wall_K"] < basis["T_out_K"] + basis["tube_wall_excess_K"]
    # Independent vapour-phase enthalpy build (review round on e7c2531, item 2):
    # deliberately NOT the module mixture_enthalpy, so a condensing flue
    # reference cannot pass this test by construction.
    flue_total = sum(basis["flue_mol"].values())
    z_flue = {cid: y / flue_total for cid, y in basis["flue_mol"].items() if y != 0.0}

    def h_vap_flue(T: float) -> float:
        return thermo.phase_props(z_flue, T, basis["box_P_Pa"], PhaseKind.VAPOR).enthalpy

    # Eq. 2 re-evaluated at the reported bridgewall temperature: with the air at
    # the 298.15 K reference its sensible term is zero, so the firebox balance is
    # n_f*LHV = Q_radiant + n_fg*(h_fg(T_g) - h_fg_vap(298.15)), water vapour.
    n_f = result["fuel_molar_flow"]
    h_fg_ref = h_vap_flue(298.15)
    h_fg_g = h_vap_flue(result["T_bridgewall_K"])
    lhs = basis["lhv_J_per_mol"] * n_f
    rhs = result["Q_radiant_W"] + n_f * basis["nu_fg"] * (h_fg_g - h_fg_ref)
    assert lhs == pytest.approx(rhs, rel=1e-8)
    # Eq. 4 re-evaluated: the convection duty equals the flue sensible drop
    # between bridgewall and stack.
    h_fg_s = h_vap_flue(result["T_stack_K"])
    assert result["Q_convection_W"] == pytest.approx(n_f * basis["nu_fg"] * (h_fg_g - h_fg_s), rel=1e-8)


def test_no_firing_rate_refused() -> None:
    """A 0.5 m2 effective radiant plane with 20 m2 of tube area and UA_C = 1 W/K
    tops out near 0.6 MW against a 1.32 MW duty: no firing rate reaches the
    spec duty down to 20% LHV efficiency (spec refusal-table row
    'no firing rate', measured to raise at stage outer)."""
    thermo, basis = _example_basis(
        alpha_Acp_m2=0.5, exchange_factor=0.6, tube_area_m2=20.0, UA_convection_W_K=1.0
    )
    with pytest.raises(FiredHeaterConvergenceError, match="no firing rate"):
        solve_fuel_and_sections(thermo, **basis)


# ---------------------------------------------------------------------------
# Spec step 3: the FiredHeaterR1 adapter, identity and refusals
# ---------------------------------------------------------------------------


def _adapter_inlet_state(T: float = 300.0) -> Any:
    thermo = _thermo()
    return thermo.flash_pt({"C1": 1.0}, T, 5.0e5, 100.0)


def _adapter_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "T_out": 600.0,
        "dP": 1.0e4,
        "fuel_composition": {"C1": 1.0},
        "excess_air_frac": 0.15,
        "alpha_Acp_m2": 8.0,
        "exchange_factor": 0.6,
        "tube_area_radiant_m2": 200.0,
        "tube_wall_excess_K": 100.0,
        "UA_convection_W_K": 1200.0,
    }
    params.update(overrides)
    return params


def test_adapter_matches_r0_fuel_and_outlet() -> None:
    """Spec 'Reduction to the lower level': the R1 process outlet is
    bit-identical to R0's for the same T_out/dP (== on T and enthalpy), and R0
    run at the R1 efficiency reproduces the R1 fuel molar flow to 1e-10."""
    thermo = _thermo()
    inlets = {"inlet": _adapter_inlet_state()}
    r1 = FiredHeaterR1().solve(inlets, _adapter_params(), thermo)
    r0 = FiredHeater().solve(
        inlets,
        {
            "T_out": 600.0,
            "dP": 1.0e4,
            "efficiency": r1.info["efficiency_LHV"],
            "fuel_composition": {"C1": 1.0},
        },
        thermo,
    )
    assert r0.outlets["outlet"].T == r1.outlets["outlet"].T
    assert r0.outlets["outlet"].enthalpy == r1.outlets["outlet"].enthalpy
    assert r0.info["fuel_molar_flow"] == pytest.approx(r1.info["fuel_molar_flow"], rel=1e-10)


def test_adapter_info_keys() -> None:
    """All spec info keys present; power_W 0; Q_fired and flux consistent."""
    thermo = _thermo()
    result = FiredHeaterR1().solve({"inlet": _adapter_inlet_state()}, _adapter_params(), thermo)
    for key in (
        "Q_fired_W",
        "fuel_LHV_J_per_mol",
        "fuel_molar_flow",
        "efficiency_LHV",
        "Q_radiant_W",
        "Q_convection_W",
        "T_bridgewall_K",
        "T_stack_K",
        "T_crossover_K",
        "T_tube_wall_K",
        "T_adiabatic_K",
        "radiant_flux_W_m2",
        "air_molar_flow",
        "flue_molar_flow",
        "flue_y_O2",
    ):
        assert key in result.info, key
    assert result.power_W == 0.0
    assert result.info["Q_fired_W"] == pytest.approx(
        result.info["fuel_molar_flow"] * result.info["fuel_LHV_J_per_mol"], rel=1e-12
    )
    assert result.info["radiant_flux_W_m2"] == pytest.approx(
        result.info["Q_radiant_W"] / _adapter_params()["tube_area_radiant_m2"], rel=1e-12
    )


def test_energy_self_consistency_with_losses() -> None:
    """Spec: fuel LHV*n_f + air sensible = Q + flue sensible at T_stack +
    losses, to 1e-8 relative. Re-evaluated independently in the test from the
    reported info with direct vapour-phase builds (review round on e7c2531,
    item 2 - the flue reference must stay all-vapour or the flue water latent
    heat leaks into the closure). air_T_K 400 K and radiant_loss_frac 0.05
    make both correction terms live."""
    thermo = _thermo()
    params = _adapter_params(air_T_K=400.0, radiant_loss_frac=0.05)
    result = FiredHeaterR1().solve({"inlet": _adapter_inlet_state()}, params, thermo)
    info = result.info
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.15)
    n_f = info["fuel_molar_flow"]
    Q = result.duty_W
    air = {"N2": 0.79, "O2": 0.21}
    flue_total = sum(stoich["flue"].values())
    z_flue = {cid: y / flue_total for cid, y in stoich["flue"].items() if y != 0.0}

    def h_vap(z: dict[str, float], T: float) -> float:
        return thermo.phase_props(z, T, 101325.0, PhaseKind.VAPOR).enthalpy

    h_air = h_vap(air, 400.0) - h_vap(air, 298.15)
    h_stack = h_vap(z_flue, info["T_stack_K"])
    h_ref = h_vap(z_flue, 298.15)
    lhs = info["fuel_LHV_J_per_mol"] * n_f + n_f * stoich["nu_air"] * h_air
    rhs = (
        Q
        + n_f * stoich["nu_fg"] * (h_stack - h_ref)
        + params["radiant_loss_frac"] * info["fuel_LHV_J_per_mol"] * n_f
    )
    assert lhs == pytest.approx(rhs, rel=1e-8)


def test_flue_reference_is_all_vapour() -> None:
    """The flue reference enthalpy at 298.15 K must be the all-vapour build
    (vf = 1), matching the fuel_lhv water-as-vapour basis (review round on
    e7c2531, item 2). Measured (PR package): a flash_pt of the 15 % excess
    methane flue at 298.15 K and 1 atm condenses (vf 0.8555) and its enthalpy
    -6616.15 J/mol carries the condensed water latent heat, while the
    vapour-phase build gives -18.92 J/mol - a 6597 J/mol of flue difference,
    about 9.8 % of the methane LHV. mixture_enthalpy must return the vapour
    value, and this test fails on the old flash_pt behaviour."""
    thermo = _thermo()
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.15)
    flue_total = sum(stoich["flue"].values())
    z_flue = {cid: y / flue_total for cid, y in stoich["flue"].items() if y != 0.0}
    flashed = thermo.flash_pt(z_flue, 298.15, 101325.0, 1.0)
    assert flashed.vapor_fraction < 1.0  # a flash_pt reference condenses the flue water
    assert flashed.enthalpy == pytest.approx(-6616.15, rel=1e-3)
    h_vapour = thermo.phase_props(z_flue, 298.15, 101325.0, PhaseKind.VAPOR).enthalpy
    assert mixture_enthalpy(thermo, stoich["flue"], 298.15, 101325.0) == pytest.approx(
        h_vapour, rel=1e-12
    )
    assert h_vapour == pytest.approx(-18.92, rel=1e-2)
    assert (h_vapour - flashed.enthalpy) * flue_total / fuel_lhv({"C1": 1.0}) == pytest.approx(
        0.098, rel=1e-2
    )


def test_stack_below_flue_dew_point_refused() -> None:
    """A wet stoichiometric methane flue (no excess air) at 10 bar box
    pressure has a 391.56 K dew point; with UA_C = 1e4 W/K the rated stack
    lands on it. The accepted solution must refuse rather than report a
    condensing stack (review round on e7c2531, item 1):
    FiredHeaterDewPointError naming the T_stack stage. The condensing regime
    is HHV territory, outside the R1 LHV basis."""
    thermo = _thermo()
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e5, 100.0)
    out = thermo.flash_pt({"C1": 1.0}, 600.0, 4.9e5, 100.0)
    Q = 100.0 * (out.enthalpy - inlet.enthalpy)
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.0)
    with pytest.raises(FiredHeaterDewPointError, match="dew point"):
        solve_fuel_and_sections(
            thermo,
            lhv_J_per_mol=fuel_lhv({"C1": 1.0}),
            flue_mol=stoich["flue"],
            air_fractions={"N2": 0.79, "O2": 0.21},
            nu_air=stoich["nu_air"],
            nu_fg=stoich["nu_fg"],
            Q_W=Q,
            F_mol_s=100.0,
            h_in_J_per_mol=inlet.enthalpy,
            T_in_K=inlet.T,
            T_out_K=out.T,
            P_out_Pa=4.9e5,
            composition={"C1": 1.0},
            air_T_K=298.15,
            box_P_Pa=1.0e6,
            alpha_Acp_m2=8.0,
            exchange_factor=0.6,
            tube_area_m2=200.0,
            h_conv_W_m2K=11.3565267,
            tube_wall_excess_K=100.0,
            UA_convection_W_K=1.0e4,
            radiant_loss_frac=0.0,
        )


def test_kern_19_1_radiant_section_documented() -> None:
    """Kern, Process Heat Transfer (1950), Ch. 19, Example 19.1: a documented
    comparison test of the radiant-section solve (NOT a V1 case - the example
    fixes the 75 % LHV efficiency as a design input and prints no convection
    UA, so it cannot anchor the R1 efficiency; review round on e7c2531,
    item 3). The fuel rate is SET from the printed 75 % efficiency and the
    50,000,000 Btu/hr absorbed duty, T_t is the printed 800 F average tube
    temperature (699.82 K), and the geometry is the printed alpha*A_cp =
    1500 ft2 = 139.3547 m2, F = 0.635, A_t = 3024 ft2 = 280.9391 m2, 25 %
    excess air preheated to 533.15 K, 2 % setting loss. Measured on the
    vapour-phase reference (PR package): T_g 1255.51 K vs the printed about
    1700 F = 1199.26 K (+4.7 %), radiant duty 11.264 MW vs the printed
    37,050,000 Btu/hr = 1.08562e7 W (+3.8 %), mean flux 40,095 W/m2 vs the
    printed 12,280 Btu/(hr ft2) = 38,738.4 W/m2 (+3.5 %); asserted at rel
    0.05. The residual gap is the 60 F chart reference vs the 298.15 K
    water-vapour formation basis and the chart flue enthalpies vs the PR
    package. The fuel carrier (nC10/C1 mix matching the printed flue
    analysis, not the printed oil LHV) and the coil fluid are documented
    carriers, as in the removed V2105 case."""
    thermo = _thermo()
    fuel = {"nC10": 0.625, "C1": 0.375}
    lhv = fuel_lhv(fuel)
    stoich = combustion_stoichiometry(fuel, None, 0.25)
    q_duty = 50.0e6 * 1055.05585262 / 3600.0  # printed 50 MBtu/hr absorbed, in W
    n_f = q_duty / (0.75 * lhv)  # the printed 75 % LHV efficiency is an input here
    t_tube = (800.0 - 32.0) * 5.0 / 9.0 + 273.15
    air = {"N2": 0.79, "O2": 0.21}
    flue_total = sum(stoich["flue"].values())
    z_flue = {cid: y / flue_total for cid, y in stoich["flue"].items() if y != 0.0}

    def h_vap(z: dict[str, float], T: float) -> float:
        return thermo.phase_props(z, T, 101325.0, PhaseKind.VAPOR).enthalpy

    air_sensible = h_vap(air, 533.15) - h_vap(air, 298.15)
    h_ref = h_vap(z_flue, 298.15)

    def balance(T_g: float) -> float:
        """Firebox balance, Eqs. 2 = 3 at the set n_f and T_t."""
        flue_sensible = stoich["nu_fg"] * (h_vap(z_flue, T_g) - h_ref)
        q_rad, _ = radiant_transfer_W(139.3547, 0.635, T_g, t_tube, 280.9391, 11.3565267)
        return (1.0 - 0.02) * lhv + stoich["nu_air"] * air_sensible - flue_sensible - q_rad / n_f

    t_g = brentq(balance, t_tube + 1e-6, 3000.0, xtol=1e-12)
    q_rad, _ = radiant_transfer_W(139.3547, 0.635, t_g, t_tube, 280.9391, 11.3565267)
    assert t_g == pytest.approx(1199.26, rel=0.05)  # printed about 1700 F
    assert q_rad == pytest.approx(1.08562e7, rel=0.05)  # printed 37,050,000 Btu/hr
    assert q_rad / 280.9391 == pytest.approx(38738.4, rel=0.05)  # printed 12,280 Btu/(hr ft2)
    assert t_g > t_tube


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"fuel_composition": None}, "fuel_composition"),
        ({"alpha_Acp_m2": 0.0}, "alpha_Acp_m2"),
        ({"tube_area_radiant_m2": -1.0}, "tube_area_radiant_m2"),
        ({"exchange_factor": 1.5}, "exchange_factor"),
        ({"excess_air_frac": -0.1}, "excess_air_frac"),
        ({"radiant_loss_frac": 0.5}, "radiant_loss_frac"),
    ],
)
def test_adapter_param_refusals(overrides: dict[str, Any], fragment: str) -> None:
    thermo = _thermo()
    with pytest.raises(FiredHeaterSpecError, match=fragment):
        FiredHeaterR1().solve({"inlet": _adapter_inlet_state()}, _adapter_params(**overrides), thermo)


def test_adapter_cooling_spec_refused() -> None:
    """A cooling spec (600 K inlet down to 300 K) is refused like R0."""
    thermo = _thermo()
    with pytest.raises(ValueError, match="cannot be satisfied by firing"):
        FiredHeaterR1().solve({"inlet": _adapter_inlet_state(T=600.0)}, _adapter_params(T_out=300.0), thermo)


def test_adapter_no_firing_rate_refused() -> None:
    """The step-2 refusal geometry through the adapter: a 0.5 m2 effective
    radiant plane, 20 m2 of tube area and UA_C 1 W/K cannot reach the 1.32 MW
    duty down to 20 % LHV efficiency."""
    thermo = _thermo()
    params = _adapter_params(alpha_Acp_m2=0.5, tube_area_radiant_m2=20.0, UA_convection_W_K=1.0)
    with pytest.raises(FiredHeaterConvergenceError, match="no firing rate"):
        FiredHeaterR1().solve({"inlet": _adapter_inlet_state()}, params, thermo)


class _HotFlueThermo:
    """Proxy refusing every flue-enthalpy request above 3500 K, so the
    adiabatic bracket [T_air, 4000 K] cannot be evaluated at its upper end.
    (With the real thermo the bracket always brackets a root: measured by
    probe, air preheat up to 3000 K still solves or fails at the outer
    stage, because the flue absorbs the LHV below 4000 K for any hydrocarbon
    fuel.) The enthalpy requests go through ``phase_props`` - the flue
    reference is a vapour-phase build, not a flash (review round on
    e7c2531, item 1) - so that is the method intercepted."""

    def __init__(self, real: Thermo) -> None:
        self._real = real

    def phase_props(self, composition: Any, T: float, P: float, kind: Any) -> Any:
        if T > 3500.0:
            raise ValueError("no flue enthalpy above 3500 K")
        return self._real.phase_props(composition, T, P, kind)

    def flash_ph(self, composition: Any, P: float, enthalpy: float, molar_flow: float) -> Any:
        return self._real.flash_ph(composition, P, enthalpy, molar_flow)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def test_ad_bracket_refused() -> None:
    """A thermo refusing enthalpies above 3500 K breaks the adiabatic bracket
    at its 4000 K end: brentq raises and the T_ad stage is named (spec
    refusal row 'a T_ad or T_g bracket failure', fragment 'adiabatic')."""
    thermo = _HotFlueThermo(_thermo())
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e5, 100.0)
    out = thermo.flash_pt({"C1": 1.0}, 600.0, 4.9e5, 100.0)
    Q = 100.0 * (out.enthalpy - inlet.enthalpy)
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.15)
    with pytest.raises(FiredHeaterConvergenceError, match="adiabatic"):
        solve_fuel_and_sections(
            thermo,
            lhv_J_per_mol=fuel_lhv({"C1": 1.0}),
            flue_mol=stoich["flue"],
            air_fractions={"N2": 0.79, "O2": 0.21},
            nu_air=stoich["nu_air"],
            nu_fg=stoich["nu_fg"],
            Q_W=Q,
            F_mol_s=100.0,
            h_in_J_per_mol=inlet.enthalpy,
            T_in_K=inlet.T,
            T_out_K=out.T,
            P_out_Pa=4.9e5,
            composition={"C1": 1.0},
            air_T_K=298.15,
            box_P_Pa=101325.0,
            alpha_Acp_m2=8.0,
            exchange_factor=0.6,
            tube_area_m2=200.0,
            h_conv_W_m2K=11.3565267,
            tube_wall_excess_K=100.0,
            UA_convection_W_K=1200.0,
            radiant_loss_frac=0.0,
        )


class _AlternatingCrossoverThermo:
    """flash_ph proxy that alternates its crossover answer between 900 K and
    300 K on every call, so the tube-wall iteration flips between
    T_t = 850 K and 550 K forever (|delta T_t| = 300 K); flash_pt passes
    through to PR."""

    def __init__(self, real: Thermo) -> None:
        self._real = real
        self._hot = False

    def flash_pt(self, composition: Any, T: float, P: float, molar_flow: float) -> Any:
        return self._real.flash_pt(composition, T, P, molar_flow)

    def flash_ph(self, composition: Any, P: float, enthalpy: float, molar_flow: float) -> Any:
        self._hot = not self._hot
        return SimpleNamespace(T=900.0 if self._hot else 300.0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def test_tube_wall_fixed_point_refused() -> None:
    """An alternating flash_ph proxy makes the tube-wall map flip between
    850 K and 550 K on every iteration: the 50-iteration cap trips (spec
    refusal row 'the T_t fixed point does not converge', message 'tube
    wall')."""
    thermo = _thermo()
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e5, 100.0)
    out = thermo.flash_pt({"C1": 1.0}, 600.0, 4.9e5, 100.0)
    Q = 100.0 * (out.enthalpy - inlet.enthalpy)
    stoich = combustion_stoichiometry({"C1": 1.0}, None, 0.15)
    stub = _AlternatingCrossoverThermo(thermo)
    with pytest.raises(FiredHeaterConvergenceError, match="tube wall"):
        solve_fuel_and_sections(
            stub,
            lhv_J_per_mol=fuel_lhv({"C1": 1.0}),
            flue_mol=stoich["flue"],
            air_fractions={"N2": 0.79, "O2": 0.21},
            nu_air=stoich["nu_air"],
            nu_fg=stoich["nu_fg"],
            Q_W=Q,
            F_mol_s=100.0,
            h_in_J_per_mol=inlet.enthalpy,
            T_in_K=inlet.T,
            T_out_K=out.T,
            P_out_Pa=4.9e5,
            composition={"C1": 1.0},
            air_T_K=298.15,
            box_P_Pa=101325.0,
            alpha_Acp_m2=8.0,
            exchange_factor=0.6,
            tube_area_m2=200.0,
            h_conv_W_m2K=11.3565267,
            tube_wall_excess_K=100.0,
            UA_convection_W_K=1200.0,
            radiant_loss_frac=0.0,
        )


def test_example_case_solves() -> None:
    """The example_case basis solves with the efficiency the corrected
    vapour-phase reference gives (measured 0.9366; the earlier 0.8253 read on
    the condensing flash_pt reference understated it by the flue water latent
    heat, about 9.8 % of fired - review round on e7c2531, item 1)."""
    feeds, params = FiredHeaterR1.example_case()
    thermo = _thermo()
    inlet_feed = feeds["inlet"]
    inlet = thermo.flash_pt(
        inlet_feed["composition"], inlet_feed["T"], inlet_feed["P"], inlet_feed["molar_flow"]
    )
    result = FiredHeaterR1().solve({"inlet": inlet}, params, thermo)
    assert 0.90 < result.info["efficiency_LHV"] < 0.97
