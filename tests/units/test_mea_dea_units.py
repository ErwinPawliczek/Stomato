"""MEA/DEA absorber and regenerator units over the shared Kent-Eisenberg module."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.mdea_absorber import MdeaAbsorber
from ngdesign.units.mdea_regenerator import MdeaRegenerator
from tests.conftest import flash_feed


def _solved(
    kind: str, thermo: Thermo, params: dict[str, Any] | None = None
) -> tuple[Any, dict[str, StreamState]]:
    unit = registry.create("unit", kind)
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit.solve(inlets, params if params is not None else defaults, thermo), inlets


# --- Registration ------------------------------------------------------------


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber", "mea_regenerator", "dea_regenerator"])
def test_registered(kind: str) -> None:
    assert kind in registry.available("unit")


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber", "mea_regenerator", "dea_regenerator"])
def test_protocol_instance(kind: str) -> None:
    unit = registry.create("unit", kind)
    if kind.endswith("absorber"):
        assert isinstance(unit, MdeaAbsorber)
    else:
        assert isinstance(unit, MdeaRegenerator)


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_absorber_ports(kind: str) -> None:
    unit = registry.create("unit", kind)
    assert unit.inlet_ports == ("gas_in", "lean_amine_in")
    assert unit.outlet_ports == ("gas_out", "rich_amine_out")


def test_amine_selection_matches_registry_name() -> None:
    assert registry.create("unit", "mea_absorber").amine == "MEA"
    assert registry.create("unit", "dea_absorber").amine == "DEA"
    assert registry.create("unit", "mea_regenerator").amine == "MEA"
    assert registry.create("unit", "dea_regenerator").amine == "DEA"


def test_amine_param_overrides_kind_alias(thermo: Thermo) -> None:
    """The absorber's `amine` param wins over the registered kind's default."""
    unit = registry.create("unit", "mdea_absorber")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    res = unit.solve(inlets, defaults, thermo)
    assert res.info["amine_per_acid_gas_removed_mol_mol"] > 0.0
    # MEA solvent with the MEA override runs; with the MDEA default it is rejected.
    feeds_mea, _ = registry.create("unit", "mdea_absorber").example_case()
    feeds_mea["lean_amine_in"]["composition"] = {"MEA": 0.15, "H2O": 0.85}
    inlets_mea = {port: flash_feed(thermo, f) for port, f in feeds_mea.items()}
    with pytest.raises(ValueError, match="carries no MDEA"):
        unit.solve(inlets_mea, defaults, thermo)
    res_mea = unit.solve(inlets_mea, {**defaults, "amine": "MEA"}, thermo)
    assert res_mea.info["amine_per_acid_gas_removed_mol_mol"] > 0.0


def test_unsupported_amine_param_raises(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="unsupported amine 'DEG'"):
        _solved("mdea_absorber", thermo, {"amine": "DEG"})


def test_solvent_must_carry_the_selected_amine(thermo: Thermo) -> None:
    """mea_absorber fed MDEA solvent fails; mdea_absorber fed MEA solvent fails."""
    for kind, solvent in (("mea_absorber", "MDEA"), ("mdea_absorber", "MEA")):
        unit = registry.create("unit", kind)
        feeds, defaults = unit.example_case()
        feeds["lean_amine_in"]["composition"] = {solvent: 0.1313, "H2O": 0.8687}
        inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
        with pytest.raises(ValueError, match=f"carries no {unit.amine}"):
            unit.solve(inlets, defaults, thermo)


# --- Absorber example cases ----------------------------------------------------


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_absorber_outlet_specs_are_met(kind: str, thermo: Thermo) -> None:
    res, _ = _solved(kind, thermo)
    gas_out: StreamState = res.outlets["gas_out"]
    assert gas_out.composition["CO2"] * 100.0 == pytest.approx(res.info["outlet_co2_molpct"], rel=1e-6)
    assert gas_out.composition["H2S"] * 1e6 == pytest.approx(res.info["outlet_h2s_ppmv"], rel=1e-6)


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_absorber_component_balances_close(kind: str, thermo: Thermo) -> None:
    res, inlets = _solved(kind, thermo)
    gas_in, lean_in = inlets["gas_in"], inlets["lean_amine_in"]
    gas_out, rich_out = res.outlets["gas_out"], res.outlets["rich_amine_out"]
    for comp in gas_in.composition:
        inlet_total = gas_in.composition[comp] * gas_in.molar_flow + (
            lean_in.composition.get(comp, 0.0) * lean_in.molar_flow
        )
        outlet_total = gas_out.composition.get(comp, 0.0) * gas_out.molar_flow + (
            rich_out.composition.get(comp, 0.0) * rich_out.molar_flow
        )
        assert outlet_total == pytest.approx(inlet_total, rel=1e-9), f"component {comp}"


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_absorber_energy_balance_closes(kind: str, thermo: Thermo) -> None:
    res, inlets = _solved(kind, thermo)
    h_in = inlets["gas_in"].enthalpy * inlets["gas_in"].molar_flow + (
        inlets["lean_amine_in"].enthalpy * inlets["lean_amine_in"].molar_flow
    )
    h_out = res.outlets["gas_out"].enthalpy * res.outlets["gas_out"].molar_flow + (
        res.outlets["rich_amine_out"].enthalpy * res.outlets["rich_amine_out"].molar_flow
    )
    assert h_in + res.duty_W == pytest.approx(h_out, rel=1e-9)


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_rich_amine_carries_the_removed_acid_gas(kind: str, thermo: Thermo) -> None:
    res, inlets = _solved(kind, thermo)
    lean_in = inlets["lean_amine_in"]
    amine_name = "MEA" if kind.startswith("mea") else "DEA"
    n_amine = lean_in.molar_flow * lean_in.composition[amine_name]
    assert res.info["rich_co2_loading"] == pytest.approx(
        res.info["lean_co2_loading"] + res.info["co2_removed_mol_s"] / n_amine, rel=1e-9
    )
    assert res.info["rich_h2s_loading"] == pytest.approx(
        res.info["lean_h2s_loading"] + res.info["h2s_removed_mol_s"] / n_amine, rel=1e-9
    )
    assert 0.1 < res.info["rich_co2_loading"] + res.info["rich_h2s_loading"] < 0.7


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_rich_loading_below_equilibrium_ceiling(kind: str, thermo: Thermo) -> None:
    res, _ = _solved(kind, thermo)
    assert res.info["rich_co2_loading"] < res.info["equilibrium_max_co2_loading"]
    assert res.info["rich_h2s_loading"] < res.info["equilibrium_max_h2s_loading"]
    assert res.info["rich_co2_loading"] < 0.9 * res.info["equilibrium_max_co2_loading"]


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_absorber_info_names_the_amine(kind: str, thermo: Thermo) -> None:
    """The selected amine is exposed on the unit, not in the float-valued info dict."""
    unit = registry.create("unit", kind)
    expected = "MEA" if kind.startswith("mea") else "DEA"
    assert unit.amine == expected
    _solved(kind, thermo)  # and the example solves


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_infeasible_circulation_raises(kind: str, thermo: Thermo) -> None:
    unit = registry.create("unit", kind)
    feeds, defaults = unit.example_case()
    feeds["lean_amine_in"]["molar_flow"] = 20.0  # starved solvent: rich loading blows past the ceiling
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="infeasible circulation"):
        unit.solve(inlets, defaults, thermo)


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber"])
def test_spec_below_lean_floor_raises(kind: str, thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="below the lean-amine equilibrium floor"):
        _solved(kind, thermo, {"h2s_out_ppmv": 1e-4})


# --- Regenerator example cases ---------------------------------------------------


@pytest.mark.parametrize("kind", ["mea_regenerator", "dea_regenerator"])
def test_regenerator_outlet_specs_are_met(kind: str, thermo: Thermo) -> None:
    res, _ = _solved(kind, thermo)
    acid_out: StreamState = res.outlets["acid_gas_out"]
    total_out = acid_out.molar_flow
    assert acid_out.composition["CO2"] * total_out == pytest.approx(res.info["co2_stripped_mol_s"], rel=1e-6)
    assert acid_out.composition["H2S"] * total_out == pytest.approx(res.info["h2s_stripped_mol_s"], rel=1e-6)


@pytest.mark.parametrize("kind", ["mea_regenerator", "dea_regenerator"])
def test_regenerator_component_balances_close(kind: str, thermo: Thermo) -> None:
    res, inlets = _solved(kind, thermo)
    rich_in = inlets["rich_amine_in"]
    lean_out, acid_out = res.outlets["lean_amine_out"], res.outlets["acid_gas_out"]
    for comp in rich_in.composition:
        inlet_total = rich_in.composition[comp] * rich_in.molar_flow
        outlet_total = lean_out.composition.get(comp, 0.0) * lean_out.molar_flow + (
            acid_out.composition.get(comp, 0.0) * acid_out.molar_flow
        )
        assert outlet_total == pytest.approx(inlet_total, rel=1e-9), f"component {comp}"


@pytest.mark.parametrize("kind", ["mea_regenerator", "dea_regenerator"])
def test_regenerator_energy_balance_closes(kind: str, thermo: Thermo) -> None:
    res, inlets = _solved(kind, thermo)
    rich_in = inlets["rich_amine_in"]
    lean_out, acid_out = res.outlets["lean_amine_out"], res.outlets["acid_gas_out"]
    h_in = rich_in.enthalpy * rich_in.molar_flow
    h_out = lean_out.enthalpy * lean_out.molar_flow + acid_out.enthalpy * acid_out.molar_flow
    assert h_in + res.duty_W == pytest.approx(h_out, rel=1e-9)


@pytest.mark.parametrize("kind", ["mea_regenerator", "dea_regenerator"])
def test_regenerator_strips_to_the_lean_spec(kind: str, thermo: Thermo) -> None:
    res, _ = _solved(kind, thermo)
    assert res.info["lean_co2_loading"] == pytest.approx(0.005, rel=0.05)
    assert res.info["lean_h2s_loading"] == pytest.approx(0.002, rel=0.05)
    assert res.info["co2_stripped_mol_s"] > 0.0
    assert res.info["h2s_stripped_mol_s"] > 0.0


# --- Determinism ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["mea_absorber", "dea_absorber", "mea_regenerator", "dea_regenerator"])
def test_solve_is_deterministic(kind: str, thermo: Thermo) -> None:
    first, _ = _solved(kind, thermo)
    second, _ = _solved(kind, thermo)
    for port in first.outlets:
        assert first.outlets[port] == second.outlets[port]
    assert first.info == second.info
