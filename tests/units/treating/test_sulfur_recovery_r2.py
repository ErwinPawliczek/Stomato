"""sulfur_recovery R2 tests (``specs/backend/units/sulfur_recovery.md``).

The oracle is the spec's calc_sulfur_recovery.py method, run here so it stays on the
current formation data: an extent-space solve of 2 H2S + SO2 -> 2 H2O + (3/6) S6 and
-> (3/8) S8 on ln K, by a different route from the element-potential Gibbs solver.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pytest
from scipy.optimize import fsolve

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Reaction
from ngdesign.units._physics.kinetics import ln_keq
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.treating.sulfur_recovery import (
    SulfurRecovery,
    SulfurRecoveryError,
    _approach_extent,
)
from ngdesign.units.treating.sulfur_recovery_r2 import SulfurRecoveryR2, _converter_equilibrium

GAS = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0}
SPECIES = ["H2S", "SO2", "H2O", "S6", "S8", "N2"]


def _claus(sulfur: str, nu: float) -> Reaction:
    return Reaction(
        id=f"claus_{sulfur}",
        stoichiometry={"H2S": -2.0, "SO2": -1.0, "H2O": 2.0, sulfur: nu},
        base_component="SO2",
        provenance="Claus reaction, test oracle",
        equilibrium={"form": "from_gibbs"},
    )


def _extent_space(t: float, p: float = 1.3e5) -> dict[str, float]:
    """Solve ln Q = ln K for both Claus routes on ideal-gas activities, by hand."""
    routes = (_claus("S6", 0.5), _claus("S8", 0.375))
    ln_k = [ln_keq(r, t) for r in routes]

    def flows(u: Any) -> dict[str, float]:
        """Unknowns keep every trial positive: the logit of the SO2 consumed, and of its S6 share."""
        consumed = 1.0 / (1.0 + math.exp(-u[0]))
        share = 1.0 / (1.0 + math.exp(-u[1]))
        out = dict(GAS)
        for reaction, x in zip(routes, (consumed * share, consumed * (1.0 - share)), strict=True):
            for cid, nu in reaction.stoichiometry.items():
                out[cid] = out.get(cid, 0.0) + nu * x
        return out

    def residual(u: Any) -> list[float]:
        n = flows(u)
        total = sum(n.values())
        return [
            sum(nu * math.log(n[cid] / total * p / 1.0e5) for cid, nu in r.stoichiometry.items()) - k
            for r, k in zip(routes, ln_k, strict=True)
        ]

    root, _, status, message = fsolve(residual, [1.0, 0.0], xtol=1e-13, full_output=True)
    assert status == 1, message
    return flows(root)


@pytest.mark.parametrize("t", [500.0, 550.0, 600.0])
def test_converter_matches_the_extent_space_solve(t: float) -> None:
    expected = _extent_space(t)
    out = _converter_equilibrium(GAS, t, 1.3e5, SPECIES)
    for cid in ("H2S", "SO2", "H2O", "S6", "S8"):
        assert out[cid] == pytest.approx(expected[cid], rel=1e-7), cid
    assert out["N2"] == pytest.approx(10.0, rel=1e-10)


def test_conversion_falls_with_temperature() -> None:
    conv = [1.0 - _converter_equilibrium(GAS, t, 1.3e5, SPECIES)["H2S"] / 2.0 for t in (500.0, 550.0, 600.0)]
    assert conv[0] > conv[1] > conv[2]


def test_reduces_to_r0_on_its_species_set() -> None:
    """One degree of freedom, the Claus extent: R0's own approach bisection, to 1e-10."""
    gas = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0, "CO2": 1.0}
    claus = _claus("S8", 0.375)
    xi, _ = _approach_extent(gas, claus, 473.0, 30.0, 1.5e5)
    out = _converter_equilibrium(gas, 503.0, 1.5e5, ["H2S", "SO2", "H2O", "S8", "N2", "CO2"])
    assert out["H2S"] == pytest.approx(2.0 - 2.0 * xi, rel=1e-10)
    assert out["SO2"] == pytest.approx(1.0 - xi, rel=1e-10)
    assert out["H2O"] == pytest.approx(4.0 + 2.0 * xi, rel=1e-10)
    assert out["S8"] == pytest.approx(0.375 * xi, rel=1e-10)


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
    assert r2.outlets["sulfur_out"].molar_flow == pytest.approx(
        r0.outlets["sulfur_out"].molar_flow, rel=1e-12
    )
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
