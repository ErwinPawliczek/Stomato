"""Gibbs equilibrium: optimality conditions, cross-checks and physical trends."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.chem import equilibrium as eq
from ngdesign.chem import thermochem as tc
from ngdesign.chem.thermochem import P_STANDARD, R, species_thermo
from ngdesign.contracts.reactions import Equilibrium, Reaction
from ngdesign.units._physics import gibbs as unit_gibbs
from ngdesign.units._physics import kinetics as unit_kinetics

REFORMING = ["CH4", "H2O", "CO", "CO2", "H2"]


def _all_gas(*keys: str) -> dict[str, str]:
    return {k: "gas" for k in keys}


def _k_ratio(result: eq.EquilibriumResult, nu: dict[str, float]) -> float:
    """Π a_i^ν_i at the solution."""
    total = result.gas_total
    value = 0.0
    for key, coefficient in nu.items():
        value += coefficient * (math.log(result.gas[key] / total) + math.log(result.P / P_STANDARD))
    return value


def test_solution_satisfies_every_independent_reaction() -> None:
    result = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 3.0}, REFORMING, 1000.0, 2e5)
    srm = tc.reaction_thermo("CH4 + H2O -> CO + 3 H2", 1000.0, phases=_all_gas("CH4", "H2O", "CO", "H2"))
    wgs = tc.reaction_thermo("CO + H2O -> CO2 + H2", 1000.0, phases=_all_gas("CO", "H2O", "CO2", "H2"))
    assert _k_ratio(result, {"CH4": -1, "H2O": -1, "CO": 1, "H2": 3}) == pytest.approx(srm.lnK, abs=1e-8)
    assert _k_ratio(result, {"CO": -1, "H2O": -1, "CO2": 1, "H2": 1}) == pytest.approx(wgs.lnK, abs=1e-8)


def test_element_balance_is_exact() -> None:
    result = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 3.0}, REFORMING, 1000.0, 2e5)
    g = result.gas
    assert g["CH4"] + g["CO"] + g["CO2"] == pytest.approx(1.0, abs=1e-10)
    assert 4 * g["CH4"] + 2 * g["H2O"] + 2 * g["H2"] == pytest.approx(10.0, abs=1e-10)
    assert g["H2O"] + g["CO"] + 2 * g["CO2"] == pytest.approx(3.0, abs=1e-10)


def test_answer_is_independent_of_how_the_feed_is_written() -> None:
    """Same atoms, same equilibrium: the defining property of a state function."""
    a = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 1.0}, REFORMING, 1100.0, 1e5)
    b = eq.gibbs_equilibrium({"CO": 1.0, "H2": 3.0}, REFORMING, 1100.0, 1e5)
    for key in REFORMING:
        assert a.gas[key] == pytest.approx(b.gas[key], rel=1e-7, abs=1e-12)


def test_gibbs_energy_is_a_minimum() -> None:
    """Moving along the reaction away from the solution raises G."""
    result = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, ["N2", "H2", "NH3"], 700.0, 1e7)

    def gibbs(n: dict[str, float]) -> float:
        total = sum(n.values())
        return math.fsum(
            ni
            * (species_thermo(k).g(700.0) + R * 700.0 * (math.log(ni / total) + math.log(1e7 / P_STANDARD)))
            for k, ni in n.items()
        )

    base = dict(result.gas)
    assert gibbs(base) == pytest.approx(result.gibbs, rel=1e-9)
    for step in (1e-3, -1e-3):
        moved = {"N2": base["N2"] - step, "H2": base["H2"] - 3 * step, "NH3": base["NH3"] + 2 * step}
        assert gibbs(moved) > result.gibbs


def test_cross_check_with_the_reactor_units_gibbs_minimiser() -> None:
    """The flowsheet path and this one share a solver and data, so they agree exactly."""
    species = ["CO", "H2O", "CO2", "H2"]
    n_in = {"CO": 1.0, "H2O": 1.0}
    T, P = 1000.0, 1e5
    theirs = unit_gibbs.gibbs_minimum(species, [], n_in, T, P)
    # and the equilibrium reactor's ln K holds at the Gibbs reactor's composition
    reaction = Reaction(
        id="wgs",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        provenance="test",
        equilibrium=Equilibrium(form="from_gibbs"),
    )
    assert theirs["CO2"] * theirs["H2"] / (theirs["CO"] * theirs["H2O"]) == pytest.approx(
        math.exp(unit_kinetics.ln_keq(reaction, T)), rel=1e-6
    )
    ours = eq.gibbs_equilibrium(n_in, species, T, P)
    assert ours.gas["H2"] == pytest.approx(theirs["H2"], rel=1e-12)


def test_inerts_dilute_but_do_not_react() -> None:
    """They carry no atoms: an inert that shares elements with the species stays put."""
    species = ["CH4", "H2O", "CO", "CO2", "H2"]
    plain = unit_gibbs.gibbs_minimum(species, [], {"CH4": 1.0, "H2O": 1.0}, 900.0, 1e5)
    diluted = unit_gibbs.gibbs_minimum(species, ["N2"], {"CH4": 1.0, "H2O": 1.0, "N2": 5.0}, 900.0, 1e5)
    assert diluted["CH4"] < plain["CH4"]  # a mole-increasing reaction gains from dilution
    by_species = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 1.0, "N2": 5.0}, [*species, "N2"], 900.0, 1e5)
    assert diluted["H2"] == pytest.approx(by_species.gas["H2"], rel=1e-9)


def test_le_chatelier_pressure() -> None:
    species = ["N2", "H2", "NH3"]
    low = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 700.0, 1e6)
    high = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 700.0, 1e7)
    assert high.gas["NH3"] > low.gas["NH3"]


def test_le_chatelier_temperature() -> None:
    species = ["N2", "H2", "NH3"]
    cool = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 600.0, 1e7)
    hot = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 800.0, 1e7)
    assert cool.gas["NH3"] > hot.gas["NH3"]


def test_inert_dilution_shifts_a_mole_increasing_reaction_forward() -> None:
    species = ["CH4", "H2O", "CO", "CO2", "H2", "N2"]
    plain = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 1.0}, REFORMING, 900.0, 1e5)
    diluted = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 1.0, "N2": 5.0}, species, 900.0, 1e5)
    assert diluted.gas["CH4"] < plain.gas["CH4"]
    assert diluted.gas["N2"] == pytest.approx(5.0)


def test_solid_carbon_appears_on_cracking_and_vanishes_with_steam() -> None:
    species = ["CH4", "H2", "C(s)"]
    cracked = eq.gibbs_equilibrium({"CH4": 1.0}, species, 1200.0, 1e5)
    assert cracked.condensed.get("C(s)", 0.0) > 0.5
    lnk = tc.reaction_thermo("C(s) + 2 H2 -> CH4", 1200.0, phases={"H2": "gas", "CH4": "gas"}).lnK
    y = cracked.mole_fractions
    assert math.log(y["CH4"] / y["H2"] ** 2) == pytest.approx(lnk, abs=1e-7)

    wet = eq.gibbs_equilibrium({"CH4": 1.0, "H2O": 6.0}, [*REFORMING, "C(s)"], 1200.0, 1e5)
    assert "C(s)" not in wet.condensed


def test_condensed_water_appears_below_its_dew_point() -> None:
    species = ["H2O", "H2O(l)", "N2"]
    cold = eq.gibbs_equilibrium({"H2O": 1.0, "N2": 1.0}, species, 300.0, 101325.0)
    assert cold.condensed["H2O(l)"] > 0.9
    # the vapour left behind sits at the saturation pressure the formation data imply
    lnk = tc.reaction_thermo("H2O(l) -> H2O(g)", 300.0).lnK
    partial = cold.mole_fractions["H2O"] * 101325.0
    assert math.log(partial / P_STANDARD) == pytest.approx(lnk, abs=1e-7)
    hot = eq.gibbs_equilibrium({"H2O": 1.0, "N2": 1.0}, species, 450.0, 101325.0)
    assert hot.condensed == {}


def test_melting_emerges_from_the_gibbs_energies() -> None:
    """Aluminium melts between these temperatures with no melting point given to the solver."""
    candidates = ["Al", "Al(l)", "Al(s)"]
    assert list(eq.gibbs_equilibrium({"Al": 1.0}, candidates, 800.0, 101325.0).condensed) == ["Al(s)"]
    molten = eq.gibbs_equilibrium({"Al": 1.0}, candidates, 1100.0, 101325.0)
    assert list(molten.condensed) == ["Al(l)"]
    assert molten.excluded == ("Al(s)",)  # the solid table stops at the melting point


def test_real_gas_fugacity_raises_ammonia_yield_at_high_pressure() -> None:
    species = ["N2", "H2", "NH3"]
    ideal = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 700.0, 3e7)
    real = eq.gibbs_equilibrium(
        {"N2": 1.0, "H2": 3.0}, species, 700.0, 3e7, thermo=registry.create("thermo", "pr")
    )
    assert real.fugacity_iterations > 0
    assert real.ln_phi["NH3"] < real.ln_phi["H2"]
    assert real.gas["NH3"] > ideal.gas["NH3"]


def test_fugacity_vanishes_at_low_pressure() -> None:
    species = ["N2", "H2", "NH3"]
    ideal = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, species, 900.0, 1e3)
    real = eq.gibbs_equilibrium(
        {"N2": 1.0, "H2": 3.0}, species, 900.0, 1e3, thermo=registry.create("thermo", "pr")
    )
    assert real.gas["NH3"] == pytest.approx(ideal.gas["NH3"], rel=1e-3)


def test_flame_with_dissociation_is_cooler_than_complete_combustion() -> None:
    species = ["CH4", "O2", "N2", "CO2", "H2O", "CO", "H2", "OH", "O", "H", "NO"]
    feed = {"CH4": 1.0, "O2": 2.0, "N2": 7.52}
    flame = eq.adiabatic_equilibrium(feed, species, 101325.0)
    complete = tc.adiabatic_flame_temperature("methane")
    assert 1800.0 < flame.T < complete
    enthalpy_in = sum(n * species_thermo(k).h(tc.T_REF) for k, n in feed.items())
    assert flame.enthalpy == pytest.approx(enthalpy_in, abs=1.0)
    assert flame.gas["CO"] > 0.0 and flame.gas["NO"] > 0.0


def test_rich_flame_is_handled_where_complete_combustion_refuses() -> None:
    species = ["CH4", "O2", "N2", "CO2", "H2O", "CO", "H2"]
    flame = eq.adiabatic_equilibrium({"CH4": 1.0, "O2": 1.5, "N2": 5.64}, species)
    assert flame.gas["CO"] > 0.1 and flame.gas["H2"] > 0.1


def test_feed_element_with_no_home_is_refused() -> None:
    with pytest.raises(eq.EquilibriumError, match="S"):
        eq.gibbs_equilibrium({"H2S": 1.0}, ["H2", "H2O"], 1000.0)


def test_negative_feed_is_refused() -> None:
    with pytest.raises(eq.EquilibriumError):
        eq.gibbs_equilibrium({"CH4": -1.0}, REFORMING, 1000.0)


def test_empty_feed_is_refused() -> None:
    with pytest.raises(eq.EquilibriumError):
        eq.gibbs_equilibrium({"CH4": 0.0}, REFORMING, 1000.0)


def test_reaction_equilibrium_matches_its_constant() -> None:
    result = eq.reaction_equilibrium(["CO + H2O -> CO2 + H2"], {"CO": 1.0, "H2O": 1.0}, 900.0, 1e5)
    lnk = next(iter(result.constants.values())).lnK
    a = result.amounts
    assert math.log(a["CO2"] * a["H2"] / (a["CO"] * a["H2O"])) == pytest.approx(lnk, abs=1e-9)


def test_equimolar_shift_is_pressure_independent() -> None:
    low = eq.reaction_equilibrium(["CO + H2O -> CO2 + H2"], {"CO": 1.0, "H2O": 1.0}, 900.0, 1e5)
    high = eq.reaction_equilibrium(["CO + H2O -> CO2 + H2"], {"CO": 1.0, "H2O": 1.0}, 900.0, 1e7)
    assert low.amounts["H2"] == pytest.approx(high.amounts["H2"], rel=1e-9)


def test_reaction_and_gibbs_routes_agree_when_the_reactions_span_the_species() -> None:
    feed = {"CH4": 1.0, "H2O": 3.0}
    by_extents = eq.reaction_equilibrium(
        ["CH4 + H2O -> CO + 3 H2", "CO + H2O -> CO2 + H2"], feed, 1000.0, 2e5
    )
    by_gibbs = eq.gibbs_equilibrium(feed, REFORMING, 1000.0, 2e5)
    for key in REFORMING:
        assert by_extents.amounts[key] == pytest.approx(by_gibbs.gas[key], rel=1e-7, abs=1e-10)


def test_listed_reactions_freeze_everything_else() -> None:
    result = eq.reaction_equilibrium(
        ["CO + H2O -> CO2 + H2"], {"CO": 1.0, "H2O": 1.0, "CH4": 2.0}, 900.0, 1e5
    )
    assert result.amounts["CH4"] == 2.0


def test_reaction_equilibrium_refuses_a_condensed_term() -> None:
    with pytest.raises(eq.EquilibriumError):
        eq.reaction_equilibrium(["C(s) + O2 -> CO2"], {"O2": 1.0}, 900.0)


def test_temperature_and_pressure_take_units() -> None:
    a = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, ["N2", "H2", "NH3"], "427 degC", "100 bar")
    b = eq.gibbs_equilibrium({"N2": 1.0, "H2": 3.0}, ["N2", "H2", "NH3"], 700.15, 1e7)
    assert a.gas["NH3"] == pytest.approx(b.gas["NH3"])


@pytest.mark.parametrize("T", [300.0, 500.0, 800.0, 1000.0, 1500.0, 2500.0])
def test_exactly_stoichiometric_water_pins_its_trace_species(T: float) -> None:
    """Regression: failed at 800-1000 K, and left O2 orders too high at 300 K."""
    result = eq.gibbs_equilibrium({"H2O": 1.0}, ["H2O", "H2", "O2"], T, 101325.0)
    lnk = tc.reaction_thermo("2 H2 + O2 -> 2 H2O", T, phases=_all_gas("H2", "O2", "H2O")).lnK
    assert _k_ratio(result, {"H2": -2, "O2": -1, "H2O": 2}) == pytest.approx(lnk, abs=1e-6)
    assert result.gas["H2"] == pytest.approx(2.0 * result.gas["O2"], rel=1e-6)


@pytest.mark.parametrize("T", [700.0, 850.0, 1000.0, 1600.0])
def test_stoichiometric_methane_air_converges(T: float) -> None:
    species = ["CH4", "O2", "N2", "CO2", "H2O", "CO", "H2", "OH", "NO"]
    result = eq.gibbs_equilibrium({"CH4": 1.0, "O2": 2.0, "N2": 7.52}, species, T, 101325.0)
    assert result.gas["CO2"] == pytest.approx(1.0, rel=0.05)


def test_elements_held_only_by_condensed_species_are_handled() -> None:
    """Regression: an element no gas carries raised instead of seeding a condensed phase."""
    carbonate = eq.gibbs_equilibrium({"CO2": 1.0, "CaO": 1.0}, ["CO2", "CaO(s)", "CaCO3(s)"], 800.0, 101325.0)
    assert list(carbonate.condensed) == ["CaCO3(s)"]
    calcined = eq.gibbs_equilibrium({"CO2": 1.0, "CaO": 1.0}, ["CO2", "CaO(s)", "CaCO3(s)"], 1500.0, 101325.0)
    assert list(calcined.condensed) == ["CaO(s)"]
    assert calcined.gas["CO2"] == pytest.approx(1.0, rel=1e-8)


def test_iron_oxides_under_a_hydrogen_atmosphere() -> None:
    reduced = eq.gibbs_equilibrium(
        {"Fe2O3": 1.0, "H2": 20.0}, ["H2", "H2O", "Fe(s)", "FeO(s)", "Fe3O4(s)", "Fe2O3(s)"], 1000.0, 101325.0
    )
    assert reduced.condensed["Fe(s)"] == pytest.approx(2.0, rel=1e-6)
