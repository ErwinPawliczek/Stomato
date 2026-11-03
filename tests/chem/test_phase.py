"""Phase behaviour, with CoolProp reference equations as the independent oracle."""

from __future__ import annotations

import CoolProp.CoolProp as CP
import pytest

from ngdesign import registry
from ngdesign.chem import phase
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import chemdb
from ngdesign.data.chemdb import MissingPropertyError
from ngdesign.uom.dimension import DimensionError
from ngdesign.uom.quantity import Q


@pytest.mark.parametrize(
    ("species", "fluid", "T"),
    [
        ("water", "Water", 373.15),
        ("water", "Water", 450.0),
        ("methane", "Methane", 150.0),
        ("propane", "Propane", 300.0),
        ("benzene", "Benzene", 350.0),
        ("toluene", "Toluene", 380.0),
        ("n-hexane", "n-Hexane", 340.0),
        ("ethanol", "Ethanol", 350.0),
        ("methanol", "Methanol", 330.0),
        ("carbon dioxide", "CO2", 250.0),
        ("ammonia", "Ammonia", 280.0),
    ],
)
def test_vapour_pressure_matches_the_reference_eos(species: str, fluid: str, T: float) -> None:
    reference = CP.PropsSI("P", "T", T, "Q", 0, fluid)
    assert phase.psat(species, T).P == pytest.approx(reference, rel=0.01)


@pytest.mark.parametrize(
    "species", ["water", "benzene", "toluene", "ethanol", "n-hexane", "n-octane", "acetone"]
)
def test_normal_boiling_point_from_the_fit_matches_the_stated_tb(species: str) -> None:
    stated = chemdb.value(species, "Tb").value
    assert phase.tsat(species, 101325.0) == pytest.approx(stated, abs=1.0)


def test_psat_and_tsat_are_inverse() -> None:
    assert phase.tsat("benzene", phase.psat("benzene", 340.0).P) == pytest.approx(340.0, abs=1e-5)


def test_saturation_accepts_units_and_checks_them() -> None:
    assert phase.psat("water", "100 degC").P == pytest.approx(phase.psat("water", 373.15).P)
    with pytest.raises(DimensionError):
        phase.psat("water", "1 bar")
    assert phase.tsat("water", Q(1, "atm")) == pytest.approx(phase.tsat("water", 101325.0))


def test_outside_every_fit_is_refused_not_extrapolated() -> None:
    with pytest.raises(phase.PhaseError):
        phase.psat("water", 10.0)


def test_species_without_a_fit_says_so() -> None:
    with pytest.raises(MissingPropertyError):
        phase.psat("aspirin", 400.0)


@pytest.mark.parametrize(
    ("species", "fluid", "T"), [("benzene", "Benzene", 320.0), ("n-hexane", "n-Hexane", 320.0)]
)
def test_clausius_clapeyron_tracks_the_reference_enthalpy(species: str, fluid: str, T: float) -> None:
    molar_mass = CP.PropsSI("M", fluid)
    reference = (CP.PropsSI("H", "T", T, "Q", 1, fluid) - CP.PropsSI("H", "T", T, "Q", 0, fluid)) * molar_mass
    assert phase.hvap_clausius_clapeyron(species, T) == pytest.approx(reference, rel=0.05)


def test_phase_rule() -> None:
    assert phase.degrees_of_freedom(1, 3) == 0  # triple point
    assert phase.degrees_of_freedom(1, 2) == 1  # saturation curve
    assert phase.degrees_of_freedom(2, 2) == 2  # binary VLE: pick T and P
    assert phase.degrees_of_freedom(3, 1, reactions=1) == 3
    with pytest.raises(phase.PhaseError):
        phase.degrees_of_freedom(1, 4)


def test_fixed_points_are_ordered() -> None:
    points = phase.fixed_points("water")
    assert points.Tm is not None and points.Tb is not None and points.Tc is not None
    assert points.Tm < points.Tb < points.Tc


@pytest.mark.parametrize(
    ("T", "P", "expected"),
    [
        (298.15, 101325.0, "liquid"),
        (450.0, 101325.0, "gas"),
        (250.0, 101325.0, "solid"),
        (700.0, 3e7, "supercritical"),
        (700.0, 1e6, "gas"),
    ],
)
def test_pure_water_phase(T: float, P: float, expected: str) -> None:
    assert phase.pure_phase("water", T, P) == expected


def test_raoult_bubble_and_dew_bound_the_two_phase_region() -> None:
    z = {"benzene": 0.5, "toluene": 0.5}
    T = 360.0
    assert phase.raoult_dew_pressure(z, T) < phase.raoult_bubble_pressure(z, T)
    assert phase.raoult_bubble_pressure({"benzene": 1.0}, T) == pytest.approx(phase.psat("benzene", T).P)


def test_raoult_bubble_temperature_lies_between_the_pure_boilers() -> None:
    T = phase.raoult_bubble_temperature({"benzene": 0.5, "toluene": 0.5}, 101325.0)
    assert phase.tsat("benzene", 101325.0) < T < phase.tsat("toluene", 101325.0)


def test_raoult_flash_closes_the_material_balance() -> None:
    z = {"benzene": 0.4, "toluene": 0.6}
    T = 365.0
    P = 0.5 * (phase.raoult_bubble_pressure(z, T) + phase.raoult_dew_pressure(z, T))
    flash = phase.raoult_flash(z, T, P)
    assert 0.0 < flash.vapour_fraction < 1.0
    vf = flash.vapour_fraction
    for key, value in z.items():
        assert vf * flash.y[key] + (1.0 - vf) * flash.x[key] == pytest.approx(value)
        assert flash.y[key] == pytest.approx(flash.K[key] * flash.x[key])
    assert flash.y["benzene"] > z["benzene"]  # the light key concentrates in the vapour


def test_relative_volatility_of_the_lighter_species_exceeds_one() -> None:
    assert phase.relative_volatility("benzene", "toluene", 360.0) > 1.0


@pytest.fixture(scope="module")
def nrtl() -> Thermo:
    package: Thermo = registry.create("thermo", "nrtl_ig")
    return package


@pytest.fixture(scope="module")
def pr() -> Thermo:
    package: Thermo = registry.create("thermo", "pr")
    return package


def test_txy_stays_between_the_pure_boiling_points(nrtl: Thermo) -> None:
    diagram = phase.txy(nrtl, "MeOH", "H2O", 101325.0, points=7)
    assert diagram.kind == "Txy"
    assert all(y > x for x, y in zip(diagram.x, diagram.y, strict=True))  # methanol is lighter
    assert list(diagram.values) == sorted(diagram.values, reverse=True)  # T falls as x rises


def test_pxy_rises_with_the_light_key(pr: Thermo) -> None:
    diagram = phase.pxy(pr, "C1", "C3", 250.0, points=5)
    assert list(diagram.values) == sorted(diagram.values)


def test_ethanol_water_azeotrope() -> None:
    # Edinburgh Azeotrope Database, the same pin tests/thermo/test_gamma_phi.py carries:
    # 78.20 C at 101.325 kPa, 4.40 wt% water. Wilson is one of the rows pinned there.
    azeotrope = phase.find_azeotrope(registry.create("thermo", "wilson_ig"), "EtOH", "H2O", 101325.0)
    assert azeotrope is not None
    assert azeotrope.T == pytest.approx(78.20 + 273.15, abs=0.5)
    # T(x) varies by about 0.01 K across x = 0.85-0.90, so temperature pins this far harder
    # than composition: these Wilson parameters put the extremum at 13 mol% water.
    assert 1.0 - azeotrope.x == pytest.approx(0.10532, abs=0.03)


def test_zeotropic_pair_has_no_azeotrope(nrtl: Thermo) -> None:
    assert phase.find_azeotrope(nrtl, "MeOH", "H2O", 101325.0, points=9) is None


def test_phase_envelope_of_a_natural_gas_binary(pr: Thermo) -> None:
    envelope = phase.phase_envelope(pr, {"C1": 0.8, "C3": 0.2}, 180.0, 300.0, points=13)
    assert envelope.P_bubble
    assert envelope.cricondenbar >= max(envelope.P_bubble)
    assert 200.0 < envelope.cricondentherm <= 300.0


def test_ideal_solubility_is_one_at_the_melting_point() -> None:
    Tm = chemdb.value("naphthalene", "Tm").value
    assert phase.ideal_solubility("naphthalene", Tm) == pytest.approx(1.0)
    assert 0.0 < phase.ideal_solubility("naphthalene", Tm - 40.0) < 1.0


def test_eutectic_lies_below_both_melting_points() -> None:
    result = phase.eutectic("naphthalene", "biphenyl")
    assert result.T < chemdb.value("naphthalene", "Tm").value
    assert result.T < chemdb.value("biphenyl", "Tm").value
    assert 0.0 < result.x_a < 1.0
    # on both liquidus curves at once
    assert phase.ideal_solubility("naphthalene", result.T) == pytest.approx(result.x_a)
    assert phase.ideal_solubility("biphenyl", result.T) == pytest.approx(1.0 - result.x_a)


def test_raoult_flash_is_single_phase_outside_the_envelope() -> None:
    """Regression: returned vapour fractions of 1.68 and -0.16."""
    z = {"benzene": 0.4, "toluene": 0.6}
    T = 365.0
    above = phase.raoult_flash(z, T, 1.1 * phase.raoult_bubble_pressure(z, T))
    below = phase.raoult_flash(z, T, 0.9 * phase.raoult_dew_pressure(z, T))
    assert above.vapour_fraction == 0.0
    assert above.x == pytest.approx(z)
    assert sum(above.y.values()) == pytest.approx(1.0)
    assert below.vapour_fraction == 1.0
    assert below.y == pytest.approx(z)
    assert sum(below.x.values()) == pytest.approx(1.0)
