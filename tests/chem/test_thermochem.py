"""Thermochemistry against NIST-JANAF log Kf, CoolProp and calorimetric data.

The oracles are independent of the code path under test: JANAF's own log Kf columns
are compared with values rebuilt from H and S, reaction heats from formation data
with measured heats of combustion, and ideal-gas Cp with the CoolProp reference EOS.
"""

from __future__ import annotations

import math

import CoolProp.CoolProp as CP
import pytest

from ngdesign.chem import stoichiometry as stoich
from ngdesign.chem import thermochem as tc
from ngdesign.chem.thermochem import T_REF, R, species_thermo
from ngdesign.contracts.reactions import Equilibrium, Reaction
from ngdesign.data import chemdb
from ngdesign.data.chemdb import MissingPropertyError
from ngdesign.units._physics import kinetics as unit_kinetics
from ngdesign.uom.quantity import Q


def _janaf_rows(cas: str, label: str = "g") -> list[dict[str, float]]:
    for rows in chemdb.janaf(cas).values():
        if rows[0]["phase"] == label:
            return rows
    raise AssertionError(f"no JANAF table {label} for {cas}")


@pytest.mark.parametrize(
    ("equation", "product", "phases"),
    [
        ("C + 2 H2 -> CH4", "CH4", {"C": "solid", "H2": "gas", "CH4": "gas"}),
        ("C + O2 -> CO2", "CO2", {"C": "solid", "O2": "gas", "CO2": "gas"}),
        ("2 H2 + O2 -> 2 H2O", "H2O", {"H2": "gas", "O2": "gas", "H2O": "gas"}),
        ("N2 + 3 H2 -> 2 NH3", "NH3", {"N2": "gas", "H2": "gas", "NH3": "gas"}),
    ],
)
@pytest.mark.parametrize("T", [500.0, 1000.0, 1500.0])
def test_rebuilt_equilibrium_constant_matches_the_janaf_log_kf_column(
    equation: str, product: str, phases: dict[str, str], T: float
) -> None:
    result = tc.reaction_thermo(equation, T, phases=phases, hf_source="janaf")
    nu_product = stoich.parse_equation(equation).nu[product]
    rows = _janaf_rows(chemdb.find(product).cas)
    tabulated = next(r["logKf"] for r in rows if r["T"] == T)
    assert result.lnK / nu_product / math.log(10.0) == pytest.approx(tabulated, abs=0.003)


def test_hermite_reproduces_the_table_between_a_consistent_interval() -> None:
    species = species_thermo("CO2", "gas", "janaf")
    rows = _janaf_rows(species.cas)
    for row in rows[3:12]:
        assert species.s(row["T"]) == pytest.approx(row["S"], abs=1e-9)
        assert species.h(row["T"]) - species.hf298 == pytest.approx(row["H_H298"], abs=1e-6)


@pytest.mark.parametrize("T", [350.0, 780.0, 1234.0])
def test_h_and_s_stay_consistent_with_cp_between_nodes(T: float) -> None:
    species = species_thermo("H2O", "gas")
    h = 0.5
    assert (species.h(T + h) - species.h(T - h)) / (2 * h) == pytest.approx(species.cp(T), rel=2e-3)
    assert (species.s(T + h) - species.s(T - h)) / (2 * h) == pytest.approx(species.cp(T) / T, rel=2e-3)


@pytest.mark.parametrize(
    ("species", "fluid"),
    [
        ("methane", "Methane"),
        ("water", "Water"),
        ("carbon dioxide", "CO2"),
        ("nitrogen", "Nitrogen"),
        ("ammonia", "Ammonia"),
    ],
)
@pytest.mark.parametrize("T", [300.0, 600.0])
def test_ideal_gas_cp_matches_the_reference_eos(species: str, fluid: str, T: float) -> None:
    reference = CP.PropsSI("CP0MOLAR", "T", T, "P", 1e3, fluid)
    # within 1 %: JANAF and the reference EOS's ideal part are separate evaluations
    assert species_thermo(species).cp(T) == pytest.approx(reference, rel=0.01)


@pytest.mark.parametrize(
    "equation", ["N2 + 3 H2 -> 2 NH3", "CO + H2O -> CO2 + H2", "CH4 + H2O -> CO + 3 H2", "CO + 2 H2 -> CH3OH"]
)
@pytest.mark.parametrize("T", [600.0, 900.0, 1200.0])
def test_van_t_hoff_and_gibbs_helmholtz_hold(equation: str, T: float) -> None:
    all_gas = {t.key: "gas" for t in stoich.parse_equation(equation).terms}
    h = 0.5
    centre = tc.reaction_thermo(equation, T, phases=all_gas)
    up = tc.reaction_thermo(equation, T + h, phases=all_gas)
    down = tc.reaction_thermo(equation, T - h, phases=all_gas)
    assert (up.lnK - down.lnK) / (2 * h) == pytest.approx(centre.dH / (R * T * T), rel=2e-3, abs=1e-5)
    assert centre.dG == pytest.approx(centre.dH - T * centre.dS)
    assert (up.dH - down.dH) / (2 * h) == pytest.approx(centre.dCp, rel=5e-3, abs=0.05)


def test_hess_law_cycle_closes() -> None:
    first = tc.reaction_thermo("C(s) + 1/2 O2 -> CO", 800.0, phases={"O2": "gas", "CO": "gas"})
    second = tc.reaction_thermo("CO + 1/2 O2 -> CO2", 800.0, phases={"O2": "gas", "CO": "gas", "CO2": "gas"})
    total = tc.reaction_thermo("C(s) + O2 -> CO2", 800.0, phases={"O2": "gas", "CO2": "gas"})
    assert first.dH + second.dH == pytest.approx(total.dH, abs=1e-6)
    assert first.dG + second.dG == pytest.approx(total.dG, abs=1e-6)


def test_reversing_a_reaction_negates_it() -> None:
    forward = tc.reaction_thermo("N2 + 3 H2 -> 2 NH3", 700.0, phases={"N2": "gas", "H2": "gas", "NH3": "gas"})
    reverse = tc.reaction_thermo("2 NH3 -> N2 + 3 H2", 700.0, phases={"N2": "gas", "H2": "gas", "NH3": "gas"})
    assert forward.lnK == pytest.approx(-reverse.lnK)


def test_enthalpy_of_vaporisation_of_water_from_formation_data() -> None:
    hvap = tc.reaction_thermo("H2O(l) -> H2O(g)", T_REF).dH
    molar = CP.PropsSI("M", "Water")
    reference = (
        CP.PropsSI("H", "T", T_REF, "Q", 1, "Water") - CP.PropsSI("H", "T", T_REF, "Q", 0, "Water")
    ) * molar
    assert hvap == pytest.approx(reference, rel=0.005)


@pytest.mark.parametrize(
    ("fuel", "phase"),
    [
        ("methane", "gas"),
        ("ethane", "gas"),
        ("propane", "gas"),
        ("n-butane", "gas"),
        ("benzene", "liquid"),
        ("n-hexane", "liquid"),
        ("methanol", "liquid"),
        ("ethanol", "liquid"),
    ],
)
def test_heat_of_combustion_from_formation_matches_calorimetry(fuel: str, phase: str) -> None:
    """Hess: Δ_cH° built from ΔfH° against WebBook-measured combustion enthalpies."""
    measured = chemdb.values(fuel, f"Hc_{phase}")
    assert measured, f"no measured combustion enthalpy for {fuel}"
    value = tc.heating_value(fuel, fuel_phase=phase)
    assert value.hhv_molar == pytest.approx(-measured[0].value, rel=0.005)


def test_lhv_is_below_hhv_by_the_heat_of_vaporisation_of_the_water() -> None:
    value = tc.heating_value("methane")
    hvap = tc.reaction_thermo("H2O(l) -> H2O(g)", T_REF).dH
    assert value.hhv_molar - value.lhv_molar == pytest.approx(2.0 * hvap)
    assert value.hhv_mass == pytest.approx(value.hhv_molar / (chemdb.find("methane").mw * 1e-3))  # type: ignore[operator]


def test_combustion_equation_handles_sulfur_and_nitrogen() -> None:
    assert stoich.parse_equation(str(tc.combustion_equation("thiophene"))).is_balanced
    assert stoich.parse_equation(str(tc.combustion_equation("pyridine"))).is_balanced
    with pytest.raises(tc.ThermochemError):
        tc.combustion_equation("sodium chloride")


def test_adiabatic_flame_temperature_closes_its_energy_balance_and_falls_when_lean() -> None:
    stoichiometric = tc.adiabatic_flame_temperature("methane")
    lean = tc.adiabatic_flame_temperature("methane", phi=0.6)
    assert 1500.0 < lean < stoichiometric < 3000.0
    reactants = (
        species_thermo("methane").h(T_REF)
        + 2 * species_thermo("O2").h(T_REF)
        + 7.52 * species_thermo("N2").h(T_REF)
    )
    products = (
        species_thermo("CO2").h(stoichiometric)
        + 2 * species_thermo("H2O").h(stoichiometric)
        + 7.52 * species_thermo("N2").h(stoichiometric)
    )
    assert products == pytest.approx(reactants, abs=1e-2)


def test_rich_mixtures_are_refused_by_the_complete_combustion_model() -> None:
    with pytest.raises(tc.ThermochemError):
        tc.adiabatic_flame_temperature("methane", phi=1.2)


def test_stable_phase_follows_the_data() -> None:
    assert tc.stable_phase("water", 298.15) == "liquid"
    assert tc.stable_phase("water", 500.0) == "gas"
    assert tc.stable_phase("naphthalene", 298.15) == "solid"
    assert tc.stable_phase("C", 298.15) == "solid"
    assert tc.stable_phase("O2", 298.15) == "gas"
    assert tc.stable_phase("Br2", 298.15) == "liquid"


def test_a_stable_phase_without_data_falls_to_the_next_that_has_it() -> None:
    # JANAF carries no ice table and no source here states ΔfH° of ice.
    assert chemdb.maybe("water", "Hf_solid") is None
    assert tc.stable_phase("water", 250.0) == "liquid"


def test_default_phases_change_with_temperature() -> None:
    cold = tc.reaction_thermo("2 H2 + O2 -> 2 H2O", T_REF)
    hot = tc.reaction_thermo("2 H2 + O2 -> 2 H2O", 500.0)
    assert cold.species["H2O"].phase == "liquid"
    assert hot.species["H2O"].phase == "gas"


def test_explicit_phase_suffix_wins() -> None:
    gas = tc.reaction_thermo("H2 + 1/2 O2 -> H2O(g)", T_REF)
    liquid = tc.reaction_thermo("H2 + 1/2 O2 -> H2O(l)", T_REF)
    assert gas.dH > liquid.dH


def test_temperature_outside_a_model_is_refused_not_extrapolated() -> None:
    with pytest.raises(tc.TemperatureRangeError):
        species_thermo("CH4").h(50.0)


def test_coarse_models_name_themselves() -> None:
    models = {
        species_thermo(q, phase).model.split(":")[0] for q, phase in (("CH4", "gas"), ("toluene", "liquid"))
    }
    assert "janaf" in models


def test_every_result_carries_its_provenance() -> None:
    result = tc.reaction_thermo("CH4 + 2 O2 -> CO2 + 2 H2O", 800.0)
    trail = result.provenance()
    assert set(trail) == {"CH4", "O2", "CO2", "H2O"}
    assert all("hf298" in entry and "shape" in entry for entry in trail.values())


def test_missing_data_refuses_rather_than_defaulting() -> None:
    with pytest.raises(MissingPropertyError):
        species_thermo("water", "gas", "no_such_source")


def test_temperature_takes_units_at_the_edge() -> None:
    a = tc.reaction_thermo("N2 + 3 H2 -> 2 NH3", "400 degC", phases={"N2": "gas", "H2": "gas", "NH3": "gas"})
    b = tc.reaction_thermo(
        "N2 + 3 H2 -> 2 NH3", Q(673.15, "K"), phases={"N2": "gas", "H2": "gas", "NH3": "gas"}
    )
    assert a.lnK == pytest.approx(b.lnK)


def test_kc_from_k_applies_the_mole_change() -> None:
    assert tc.kp_to_kc(2.0, 0.0, 500.0) == 2.0
    assert tc.kp_to_kc(1.0, 1.0, 500.0) == pytest.approx(1e5 / (R * 500.0))


def test_crossover_temperature_of_the_water_gas_shift() -> None:
    T = tc.equilibrium_temperature("CO + H2O -> CO2 + H2")
    assert tc.reaction_thermo(
        "CO + H2O -> CO2 + H2", T, phases={k: "gas" for k in ("CO", "H2O", "CO2", "H2")}
    ).dG == pytest.approx(0.0, abs=1e-2)


def test_cross_check_with_the_reactor_units_databank_path() -> None:
    """The flowsheet's ln_keq and this engine read one set of species models."""
    reaction = Reaction(
        id="wgs",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        provenance="test",
        equilibrium=Equilibrium(form="from_gibbs"),
    )
    T = 900.0
    here = tc.reaction_thermo(
        "CO + H2O -> CO2 + H2", T, phases={k: "gas" for k in ("CO", "H2O", "CO2", "H2")}
    )
    assert here.lnK == pytest.approx(unit_kinetics.ln_keq(reaction, T), rel=1e-9)
    assert here.dH == pytest.approx(unit_kinetics.heat_of_reaction(reaction, T), rel=1e-9)


def test_sulfur_above_boiling_means_its_reference_vapour_not_atomic_gas() -> None:
    """Regression: gave -577.8 kJ through S(g); the JANAF ΔfH column of SO2 at 1000 K rules."""
    rows = _janaf_rows(chemdb.find("SO2").cas)
    tabulated = next(r["Hf"] for r in rows if r["T"] == 1000.0)
    assert tc.reaction_thermo("S + O2 -> SO2", 1000.0).dH == pytest.approx(tabulated, abs=2500.0)


def test_polymorphs_take_enthalpy_and_shape_from_one_table() -> None:
    """Regression: Al2O3 mixed alpha's ΔfH with another table's Cp(T)."""
    alumina = species_thermo("Al2O3", "solid")
    table = alumina.model.split(":")[1]
    rows = chemdb.janaf("Al2O3")[table]
    assert alumina.hf298 == next(r["Hf"] for r in rows if r["T"] == T_REF)
    # the stable polymorph has the lowest G°298 of the solid tables
    solids = [t for t in chemdb.janaf("Al2O3").values() if t[0]["phase"] in ("cr", "cr,l")]
    lowest = min(next(r["Hf"] - T_REF * r["S"] for r in t if r["T"] == T_REF) for t in solids)
    assert alumina.g(T_REF) == pytest.approx(lowest, abs=1.0)


def test_per_mole_basis_as_written_is_respected() -> None:
    """Regression: balancing reduced 1/2 O2 to integers and doubled ΔH."""
    half = tc.reaction_thermo("H2 + 1/2 O2 -> H2O(g)", T_REF)
    whole = tc.reaction_thermo("2 H2 + O2 -> 2 H2O(g)", T_REF)
    assert whole.dH == pytest.approx(2.0 * half.dH)
