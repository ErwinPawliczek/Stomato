"""Tests for the MDEA absorber unit (Kent-Eisenberg chemistry)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.mdea_absorber import MdeaAbsorber
from tests.conftest import flash_feed


def _solved(thermo: Thermo, params: dict[str, Any] | None = None) -> Any:
    unit = registry.create("unit", "mdea_absorber")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit.solve(inlets, params if params is not None else defaults, thermo), inlets


def _lean_mdea_mol(lean_in: StreamState) -> float:
    """MDEA molar flow of the lean amine on the overall stream basis, mol/s."""
    return lean_in.molar_flow * lean_in.composition.get("MDEA", 0.0)


def test_registered() -> None:
    assert "mdea_absorber" in registry.available("unit")


def test_ports() -> None:
    unit = registry.create("unit", "mdea_absorber")
    assert unit.inlet_ports == ("gas_in", "lean_amine_in")
    assert unit.outlet_ports == ("gas_out", "rich_amine_out")


def test_protocol_instance() -> None:
    assert isinstance(registry.create("unit", "mdea_absorber"), MdeaAbsorber)


def test_outlet_specs_are_met(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    gas_out: StreamState = res.outlets["gas_out"]
    assert gas_out.composition["CO2"] * 100.0 == pytest.approx(res.info["outlet_co2_molpct"], rel=1e-6)
    assert gas_out.composition["H2S"] * 1e6 == pytest.approx(res.info["outlet_h2s_ppmv"], rel=1e-6)


def test_component_balances_close(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    gas_in = inlets["gas_in"]
    lean_in = inlets["lean_amine_in"]
    gas_out = res.outlets["gas_out"]
    rich_out = res.outlets["rich_amine_out"]
    for comp in gas_in.composition:
        inlet_total = gas_in.composition[comp] * gas_in.molar_flow + (
            lean_in.composition.get(comp, 0.0) * lean_in.molar_flow
        )
        outlet_total = gas_out.composition.get(comp, 0.0) * gas_out.molar_flow + (
            rich_out.composition.get(comp, 0.0) * rich_out.molar_flow
        )
        assert outlet_total == pytest.approx(inlet_total, rel=1e-9), f"component {comp}"


def test_energy_balance_closes(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    gas_in = inlets["gas_in"]
    lean_in = inlets["lean_amine_in"]
    gas_out = res.outlets["gas_out"]
    rich_out = res.outlets["rich_amine_out"]
    h_in = gas_in.enthalpy * gas_in.molar_flow + lean_in.enthalpy * lean_in.molar_flow
    h_out = gas_out.enthalpy * gas_out.molar_flow + rich_out.enthalpy * rich_out.molar_flow
    assert h_in + res.duty_W == pytest.approx(h_out, rel=1e-9)


def test_rich_amine_carries_the_removed_acid_gas(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    n_mdea = _lean_mdea_mol(inlets["lean_amine_in"])
    assert res.info["rich_co2_loading"] == pytest.approx(
        res.info["lean_co2_loading"] + res.info["co2_removed_mol_s"] / n_mdea, rel=1e-9
    )
    assert res.info["rich_h2s_loading"] == pytest.approx(
        res.info["lean_h2s_loading"] + res.info["h2s_removed_mol_s"] / n_mdea, rel=1e-9
    )
    # Realistic MDEA rich-loading window.
    assert 0.1 < res.info["rich_co2_loading"] + res.info["rich_h2s_loading"] < 0.7


def test_rich_loading_below_bottom_ceiling(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    assert res.info["rich_co2_loading"] < res.info["equilibrium_max_co2_loading"]
    assert res.info["rich_h2s_loading"] < res.info["equilibrium_max_h2s_loading"]
    # And the example keeps a working margin, not a knife-edge.
    assert res.info["rich_co2_loading"] < 0.9 * res.info["equilibrium_max_co2_loading"]


def test_lean_loadings_match_example_feed(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    assert res.info["lean_co2_loading"] == pytest.approx(0.005, rel=0.05)
    assert res.info["lean_h2s_loading"] == pytest.approx(0.002, rel=0.05)


def test_spec_below_lean_floor_raises(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="below the lean-amine equilibrium floor"):
        _solved(thermo, {"h2s_out_ppmv": 1e-4})


def test_infeasible_circulation_raises(thermo: Thermo) -> None:
    unit = registry.create("unit", "mdea_absorber")
    feeds, defaults = unit.example_case()
    feeds["lean_amine_in"]["molar_flow"] = 20.0  # starved solvent: rich loading blows past the ceiling
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="infeasible circulation"):
        unit.solve(inlets, defaults, thermo)


def test_sweet_gas_raises(thermo: Thermo) -> None:
    unit = registry.create("unit", "mdea_absorber")
    feeds, defaults = unit.example_case()
    sweet = {"C1": 0.9075, "C2": 0.05, "C3": 0.02, "N2": 0.0225}
    feeds["gas_in"]["composition"] = dict(sweet)
    feeds["lean_amine_in"]["composition"] = {"MDEA": 0.1313, "H2O": 0.8687}
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="no acid gas to remove"):
        unit.solve(inlets, defaults, thermo)


def test_selective_h2s_service_passes_co2(thermo: Thermo) -> None:
    # CO2 spec far above the inlet content: CO2 passes through, H2S is still treated.
    res, _ = _solved(thermo, {"co2_out_molpct": 20.0})
    assert res.info["co2_removed_mol_s"] == pytest.approx(0.0, abs=1e-12)
    assert res.info["h2s_removed_mol_s"] > 0.0
    gas_out: StreamState = res.outlets["gas_out"]
    assert gas_out.composition["H2S"] * 1e6 == pytest.approx(4.0, rel=1e-6)


def test_removal_fractions(thermo: Thermo) -> None:
    # 2 mol% CO2 spec on the wet-gas basis leaves 0.02*92.5/(1-0.02-4e-6) = 1.8878 mol/s.
    res, _ = _solved(thermo)
    assert res.info["co2_removal_fraction"] == pytest.approx(1.0 - 1.8878 / 6.0, rel=1e-3)
    assert res.info["h2s_removal_fraction"] > 0.999


def test_solve_is_deterministic(thermo: Thermo) -> None:
    first, _ = _solved(thermo)
    second, _ = _solved(thermo)
    assert first.outlets["gas_out"] == second.outlets["gas_out"]
    assert first.outlets["rich_amine_out"] == second.outlets["rich_amine_out"]
    assert first.info == second.info


def test_invalid_params_raise(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="co2_out_molpct"):
        _solved(thermo, {"co2_out_molpct": -1.0})
    with pytest.raises(ValueError, match="h2s_out_ppmv"):
        _solved(thermo, {"h2s_out_ppmv": 0.0})


def test_unflashed_lean_amine_raises(thermo: Thermo) -> None:
    unit = registry.create("unit", "mdea_absorber")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    lean = inlets["lean_amine_in"].model_copy(update={"phases": []})
    with pytest.raises(ValueError, match="flashed stream"):
        unit.solve({"gas_in": inlets["gas_in"], "lean_amine_in": lean}, defaults, thermo)
