"""Liquid solutions and aqueous speciation in the Gibbs solver.

Oracles: Raoult's law on the cited fits; CRC-derived constants of the solver's own
potentials; pure-water and strong-electrolyte limits; pKw against the Bandura & Lvov
(2006) table; the textbook acid constants and solubility products as sanity anchors, with
their tolerance stated.
"""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.chem import phase
from ngdesign.chem.thermochem import reaction_thermo
from ngdesign.data import chemdb
from ngdesign.data.species_models import species_thermo
from ngdesign.units._physics.gibbs_phases import (
    EquilibriumError,
    davies_ln_gamma,
    debye_huckel_a,
    gibbs_equilibrium,
)

WATER = 55.508  # mol per kg of water, 1000/18.015268
BASE = ["H2O(aq)", "H+(aq)", "OH-(aq)"]
BTX = ["benzene", "toluene", "benzene(sln)", "toluene(sln)"]
FEED = {"benzene": 0.4, "toluene": 0.6}


def test_ions_resolve_by_charge_and_never_to_the_neutral() -> None:
    assert chemdb.find("Na+").formula == "Na+"
    assert chemdb.find("Ca2+").cas == chemdb.find("Ca+2").cas == chemdb.find("Ca^2+").cas
    assert chemdb.find("sodium").charge == 0
    with pytest.raises(chemdb.UnknownSpeciesError):
        chemdb.find("Na-")


def test_liquid_model_holds_the_vapour_pressure_fit() -> None:
    """The regression that drove the saturation model: 116 kPa against 144 kPa."""
    T = 365.0
    liquid, gas = species_thermo("benzene", "liquid"), species_thermo("benzene", "gas")
    implied = 1e5 * math.exp(-(gas.g(T) - liquid.g(T)) / (8.31446261815324 * T))
    assert liquid.model == "saturation"
    assert implied == pytest.approx(phase.psat("benzene", T).P, rel=1e-9)


def test_liquid_model_keeps_gibbs_helmholtz() -> None:
    liquid = species_thermo("benzene", "liquid")
    T, h = 340.0, 0.5
    # within the gap the model states: S absorbs ΔfH°(l) against ΔfH°(g) − ΔHvap of the fit
    assert (liquid.g(T + h) - liquid.g(T - h)) / (2 * h) == pytest.approx(-liquid.s(T), rel=2e-3)


def test_saturation_liquid_gives_a_real_heat_capacity() -> None:
    assert 120.0 < species_thermo("benzene", "liquid").cp(300.0) < 170.0


@pytest.mark.parametrize("fraction", [0.25, 0.5, 0.75])
def test_ideal_solution_reproduces_raoult_inside_the_envelope(fraction: float) -> None:
    T = 365.0
    bubble = phase.raoult_bubble_pressure(FEED, T)
    dew = phase.raoult_dew_pressure(FEED, T)
    P = dew + fraction * (bubble - dew)
    expected = phase.raoult_flash(FEED, T, P)
    result = gibbs_equilibrium(FEED, BTX, T, P)
    assert result.solution_fractions["benzene(sln)"] == pytest.approx(expected.x["benzene"], rel=1e-6)
    assert result.mole_fractions["benzene"] == pytest.approx(expected.y["benzene"], rel=1e-6)
    assert result.gas_total == pytest.approx(expected.vapour_fraction, rel=1e-5)


def test_single_phase_ends_of_the_envelope() -> None:
    T = 365.0
    vapour = gibbs_equilibrium(FEED, BTX, T, 0.9 * phase.raoult_dew_pressure(FEED, T))
    assert sum(vapour.solution.values()) == 0.0
    assert vapour.gas["benzene"] == pytest.approx(0.4)
    liquid = gibbs_equilibrium(FEED, BTX, T, 1.1 * phase.raoult_bubble_pressure(FEED, T))
    assert sum(liquid.gas.values()) == 0.0
    assert liquid.solution["toluene(sln)"] == pytest.approx(0.6)


def test_activity_coefficients_move_the_split_the_right_way() -> None:
    """Ethanol is above ideal in water, so it pushes more into the vapour."""
    feed = {"EtOH": 0.1, "H2O": 0.9}
    candidates = ["EtOH", "H2O", "EtOH(sln)", "H2O(sln)"]
    ideal = gibbs_equilibrium(feed, candidates, 363.15, 101325.0)
    real = gibbs_equilibrium(
        feed, candidates, 363.15, 101325.0, activity=registry.create("thermo", "wilson_ig")
    )
    assert real.fugacity_iterations > 1
    assert sum(real.gas.values()) > sum(ideal.gas.values())


def test_liquid_phase_reaction_runs_with_no_gas_at_all() -> None:
    """Esterification in solution: K from the liquid models, no gas candidate."""
    tokens = ["acetic acid(sln)", "ethanol(sln)", "ethyl acetate(sln)", "water(sln)"]
    result = gibbs_equilibrium({"acetic acid": 1.0, "ethanol": 1.0}, tokens, 333.15, 101325.0)
    x = result.solution_fractions
    ln_k = reaction_thermo(
        "acetic acid + ethanol -> ethyl acetate + water",
        333.15,
        phases={k: "liquid" for k in ("acetic acid", "ethanol", "ethyl acetate", "water")},
    ).lnK
    q = x["ethyl acetate(sln)"] * x["water(sln)"] / (x["acetic acid(sln)"] * x["ethanol(sln)"])
    assert math.log(q) == pytest.approx(ln_k, abs=1e-7)
    assert sum(result.solution.values()) == pytest.approx(2.0)


def test_pure_water_is_neutral() -> None:
    result = gibbs_equilibrium({"H2O": WATER}, BASE, 298.15)
    assert result.pH == pytest.approx(7.0, abs=0.01)
    assert result.aqueous["H+(aq)"] == pytest.approx(result.aqueous["OH-(aq)"], rel=1e-8)


#: pKw at 0.1 MPa, Bandura & Lvov, J. Phys. Chem. Ref. Data 35(1), 15-30 (2006), Table 4
#: (Model II, Eq. 39); the 100 °C entry is at saturation pressure.
BANDURA_LVOV_PKW = {25.0: 13.99, 50.0: 13.26, 75.0: 12.70, 100.0: 12.25}


@pytest.mark.parametrize(("celsius", "pkw"), sorted(BANDURA_LVOV_PKW.items()))
def test_water_ionisation_matches_the_reference_table(celsius: float, pkw: float) -> None:
    """CRC ion data at 25 °C held with a constant Cp: measured +0.008 at 25 °C, +0.018 at 50,
    +0.027 at 75 and +0.056 at 100 °C. The bound follows that drift, not a fit."""
    r = reaction_thermo("H2O(l) -> H+ + OH-", 273.15 + celsius)
    assert -r.lnK / math.log(10.0) == pytest.approx(pkw, abs=0.01 + 0.0007 * (celsius - 25.0))


def test_water_ionisation_refuses_below_the_liquid_table() -> None:
    from ngdesign.data.species_models import TemperatureRangeError

    with pytest.raises(TemperatureRangeError):
        reaction_thermo("H2O(l) -> H+ + OH-", 273.16)


def test_strong_acid_and_base_set_the_ph() -> None:
    acid = gibbs_equilibrium({"H2O": WATER, "HCl": 0.01}, [*BASE, "Cl-(aq)"], 298.15)
    # pH = -log10(0.01 γ±), with Davies at I = 0.01
    gamma = math.exp(davies_ln_gamma(1, 0.01, debye_huckel_a(298.15)))
    assert acid.pH == pytest.approx(-math.log10(0.01 * gamma), abs=1e-4)
    base = gibbs_equilibrium({"H2O": WATER, "NaOH": 0.01}, [*BASE, "Na+(aq)"], 298.15)
    assert acid.pH + base.pH == pytest.approx(14.0, abs=0.06)


def test_a_neutral_salt_leaves_the_solution_neutral() -> None:
    result = gibbs_equilibrium({"H2O": WATER, "NaCl": 0.1}, [*BASE, "Na+(aq)", "Cl-(aq)"], 298.15)
    assert result.pH == pytest.approx(7.0, abs=0.02)
    assert result.ionic_strength == pytest.approx(0.1, rel=1e-4)


@pytest.mark.parametrize("feed", [{"HCl": 0.01}, {"NaOH": 0.02}, {"NaCl": 0.05, "CO2": 0.01}])
def test_electroneutrality_is_exact(feed: dict[str, float]) -> None:
    species = [*BASE, "Cl-(aq)", "Na+(aq)", "CO2(aq)", "HCO3-(aq)", "CO3-2(aq)"]
    result = gibbs_equilibrium({"H2O": WATER, **feed}, species, 298.15)
    charge = {"H+(aq)": 1, "OH-(aq)": -1, "Cl-(aq)": -1, "Na+(aq)": 1, "HCO3-(aq)": -1, "CO3-2(aq)": -2}
    # a candidate with no element in the feed is left out of the problem
    present = {k: z for k, z in charge.items() if k in result.aqueous}
    positive = sum(result.aqueous[k] for k, z in present.items() if z > 0)
    net = sum(z * result.aqueous[k] for k, z in present.items())
    assert abs(net) < 1e-9 * max(positive, 1e-9)


def test_co2_saturated_water_matches_henry_and_the_first_dissociation() -> None:
    species = [*BASE, "CO2(aq)", "HCO3-(aq)", "CO3-2(aq)", "CO2", "H2O"]
    result = gibbs_equilibrium({"H2O": WATER, "CO2": 10.0}, species, 298.15, 101325.0)
    y = result.mole_fractions["CO2"]
    assert result.molality("CO2(aq)") == pytest.approx(0.034 * y * 1.01325, rel=0.05)
    assert result.pH == pytest.approx(3.9, abs=0.1)


def test_acid_constants_of_the_derived_data_are_near_their_accepted_values() -> None:
    """Sanity anchors, 0.1 pK: CRC ions with Henry-derived neutrals, nothing fitted."""
    assert -reaction_thermo("CO2(aq) + H2O(l) -> H+ + HCO3-").lnK / math.log(10) == pytest.approx(
        6.35, abs=0.1
    )
    assert -reaction_thermo("HCO3- -> H+ + CO3-2").lnK / math.log(10) == pytest.approx(10.33, abs=0.1)
    assert -reaction_thermo("NH4+ -> H+ + NH3(aq)").lnK / math.log(10) == pytest.approx(9.25, abs=0.1)


def test_calcite_dissolves_to_its_solubility_and_stays_solid() -> None:
    species = [*BASE, "Ca+2(aq)", "CO3-2(aq)", "HCO3-(aq)", "CO2(aq)", "CaCO3(s)"]
    result = gibbs_equilibrium({"H2O": WATER, "CaCO3": 0.1}, species, 298.15)
    assert result.condensed["CaCO3(s)"] > 0.09
    assert 8e-5 < result.molality("Ca+2(aq)") < 2e-4
    assert result.pH > 9.0


def test_aqueous_candidates_need_the_solvent() -> None:
    with pytest.raises(EquilibriumError, match="solvent"):
        gibbs_equilibrium({"HCl": 1.0}, ["H+(aq)", "Cl-(aq)"], 298.15)


def test_davies_limit_is_enforced() -> None:
    with pytest.raises(EquilibriumError, match="Davies"):
        gibbs_equilibrium({"H2O": WATER, "NaCl": 2.0}, [*BASE, "Na+(aq)", "Cl-(aq)"], 298.15)


def test_debye_huckel_a_follows_temperature() -> None:
    assert debye_huckel_a(298.15) == pytest.approx(0.51, abs=0.01)
    assert debye_huckel_a(333.15) > debye_huckel_a(298.15)


def test_ion_thermo_carries_a_named_coarse_model() -> None:
    model = species_thermo("HCO3-", "aqueous")
    assert model.model in ("vant_hoff", "constant_cp")
    assert model.provenance["hf298"].startswith("crc_aqueous")
