"""sulfur_recovery R2 tests (``specs/backend/units/sulfur_recovery.md``).

The table comes from the spec's calc_sulfur_recovery.py, an independent extent-space
solve of 2 H2S + SO2 -> 2 H2O + (3/6) S6 and -> (3/8) S8 with scipy fsolve on ln K.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.treating.sulfur_recovery import SulfurRecovery, SulfurRecoveryError
from ngdesign.units.treating.sulfur_recovery_r2 import SulfurRecoveryR2, _converter_equilibrium

GAS = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0}
SPECIES = ["H2S", "SO2", "H2O", "S6", "S8", "N2"]


@pytest.mark.parametrize(
    ("t", "h2s", "so2", "h2o", "s6", "s8"),
    [
        (500.0, 0.1484047, 0.0742023499, 5.8515953, 0.0510661578, 0.3088745),
        (550.0, 0.300279162, 0.150139581, 5.69972084, 0.0789358317, 0.259495783),
        (600.0, 0.524034079, 0.26201704, 5.47596592, 0.103411603, 0.199184908),
    ],
)
def test_converter_table(t: float, h2s: float, so2: float, h2o: float, s6: float, s8: float) -> None:
    out = _converter_equilibrium(GAS, t, 1.3e5, SPECIES)
    for cid, value in (("H2S", h2s), ("SO2", so2), ("H2O", h2o), ("S6", s6), ("S8", s8)):
        assert out[cid] == pytest.approx(value, rel=1e-6), cid
    assert out["N2"] == pytest.approx(10.0, rel=1e-10)


def test_conversion_falls_with_temperature() -> None:
    conv = [1.0 - _converter_equilibrium(GAS, t, 1.3e5, SPECIES)["H2S"] / 2.0 for t in (500.0, 550.0, 600.0)]
    assert conv[0] > conv[1] > conv[2]


def test_reduces_to_r0_on_its_species_set() -> None:
    """One degree of freedom, the Claus extent: R0's approach result to 1e-10.

    Spec values from R0's _approach_extent at 473 K + 30 K, 1.5e5 Pa.
    """
    gas = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0, "CO2": 1.0}
    out = _converter_equilibrium(gas, 503.0, 1.5e5, ["H2S", "SO2", "H2O", "S8", "N2", "CO2"])
    assert out["H2S"] == pytest.approx(0.15518331468558655, rel=1e-10)
    assert out["SO2"] == pytest.approx(0.07759165734279327, rel=1e-10)
    assert out["H2O"] == pytest.approx(5.844816685314413, rel=1e-10)
    assert out["S8"] == pytest.approx(0.34590312849645255, rel=1e-10)


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = SulfurRecoveryR2.example_case()
    return {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}


def test_elements_close_and_s6_counts(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    params = SulfurRecoveryR2.example_case()[1]
    res = SulfurRecoveryR2().solve(inlets, params, thermo)
    mass_in, atoms_in = mass_and_atoms(inlets.values())
    mass_out, atoms_out = mass_and_atoms(res.outlets.values())
    assert mass_out == pytest.approx(mass_in, rel=1e-8)
    for element, value in atoms_in.items():
        assert atoms_out[element] == pytest.approx(value, rel=1e-8), element
    sulfur = res.outlets["sulfur_out"].component_flows()
    expected = (6.0 * sulfur["S6"] + 8.0 * sulfur["S8"]) / 30.0
    assert res.info["sulfur_recovery_fraction"] == pytest.approx(expected, rel=1e-12)
    assert res.info["stage_0_T_eq_K"] == 573.0
    assert res.info["stage_1_T_eq_K"] == pytest.approx(503.15)


def test_furnace_is_r0(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    params = SulfurRecoveryR2.example_case()[1]
    r2 = SulfurRecoveryR2().solve(inlets, params, thermo)
    r0 = SulfurRecovery().solve(inlets, {**params, "catalytic_stages": []}, thermo)
    assert r2.info["burn_extent_mol_s"] == r0.info["burn_extent_mol_s"]
    assert r2.info["thermal_extent_mol_s"] == r0.info["thermal_extent_mol_s"]


def test_no_stages_is_the_furnace_alone(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    params = SulfurRecoveryR2.example_case()[1]
    r2 = SulfurRecoveryR2().solve(inlets, {**params, "catalytic_stages": []}, thermo)
    r0 = SulfurRecovery().solve(inlets, {**params, "catalytic_stages": []}, thermo)
    assert r2.outlets["sulfur_out"].molar_flow == pytest.approx(r0.outlets["sulfur_out"].molar_flow, rel=1e-12)
    assert r2.duty_W == pytest.approx(r0.duty_W, rel=1e-9)


def test_extra_species_join_the_set(thermo: Thermo) -> None:
    params = {**SulfurRecoveryR2.example_case()[1], "extra_species": ["COS", "CS2"]}
    res = SulfurRecoveryR2().solve(_inlets(thermo), params, thermo)
    assert res.info["species_set_size"] >= 9.0
    assert 0.0 < res.info["sulfur_recovery_fraction"] <= 1.0


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"catalytic_stages": [{"T": 573.0, "conversion": 0.7}]}, "R2"),
        ({"catalytic_stages": [{"T": 0.0}]}, "catalytic_stages"),
        ({"catalytic_stages": [{"T": 573.0, "approach_K": -1.0}]}, "catalytic_stages"),
        ({"catalytic_stages": [{}]}, "catalytic_stages"),
        ({"catalytic_stages": "two"}, "catalytic_stages"),
        ({"extra_species": ["SO3"]}, "extra_species"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {**SulfurRecoveryR2.example_case()[1], **change}
    with pytest.raises(SulfurRecoveryError, match=match):
        SulfurRecoveryR2().solve(_inlets(thermo), params, thermo)


def test_species_without_formation_data_named() -> None:
    with pytest.raises(SulfurRecoveryError, match="fcc_vgo"):
        import ngdesign.units.refining.fcc  # noqa: F401

        _converter_equilibrium(GAS, 500.0, 1.3e5, [*SPECIES, "fcc_vgo"])


def test_r0_refusals_propagate(thermo: Thermo) -> None:
    feeds, params = SulfurRecoveryR2.example_case()
    f = deepcopy(feeds["acid_gas_in"])
    f["composition"] = {"H2S": 0.5, "O2": 0.01, "N2": 0.49}
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    with pytest.raises(SulfurRecoveryError, match="O2"):
        SulfurRecoveryR2().solve({"acid_gas_in": inlet}, params, thermo)
