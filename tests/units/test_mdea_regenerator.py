"""Tests for the MDEA regenerator unit (Kent-Eisenberg chemistry)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.mdea_regenerator import MdeaRegenerator
from tests.conftest import flash_feed


def _solved(thermo: Thermo, params: dict[str, Any] | None = None) -> Any:
    unit = registry.create("unit", "mdea_regenerator")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit.solve(inlets, params if params is not None else defaults, thermo), inlets


def test_registered() -> None:
    assert "mdea_regenerator" in registry.available("unit")


def test_ports() -> None:
    unit = registry.create("unit", "mdea_regenerator")
    assert unit.inlet_ports == ("rich_amine_in",)
    assert unit.outlet_ports == ("lean_amine_out", "acid_gas_out")


def test_protocol_instance() -> None:
    assert isinstance(registry.create("unit", "mdea_regenerator"), MdeaRegenerator)


def test_lean_loadings_are_met(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    lean_out: StreamState = res.outlets["lean_amine_out"]
    z = lean_out.composition
    assert z["CO2"] / z["MDEA"] == pytest.approx(res.info["lean_co2_loading"], rel=1e-6)
    assert z["H2S"] / z["MDEA"] == pytest.approx(res.info["lean_h2s_loading"], rel=1e-6)


def test_solvent_components_pass_through_unstripped(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    rich_in = inlets["rich_amine_in"]
    lean_out = res.outlets["lean_amine_out"]
    for comp in ("MDEA", "H2O"):
        inlet_flow = rich_in.composition[comp] * rich_in.molar_flow
        outlet_flow = lean_out.composition[comp] * lean_out.molar_flow
        assert outlet_flow == pytest.approx(inlet_flow, rel=1e-6)


def test_stripped_acid_gas_lands_in_the_acid_gas_product(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    rich_in = inlets["rich_amine_in"]
    lean_out = res.outlets["lean_amine_out"]
    acid_out = res.outlets["acid_gas_out"]
    for comp, stripped in (("CO2", res.info["co2_stripped_mol_s"]), ("H2S", res.info["h2s_stripped_mol_s"])):
        removed = (
            rich_in.composition[comp] * rich_in.molar_flow - lean_out.composition[comp] * lean_out.molar_flow
        )
        assert removed == pytest.approx(stripped, rel=1e-6)
        assert acid_out.composition[comp] * acid_out.molar_flow == pytest.approx(stripped, rel=1e-6)
    assert set(acid_out.composition) == {"CO2", "H2S"}


def test_energy_balance_closes(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    rich_in = inlets["rich_amine_in"]
    h_in_W = rich_in.enthalpy * rich_in.molar_flow
    h_out_W = sum(s.enthalpy * s.molar_flow for s in res.outlets.values())
    assert res.duty_W == pytest.approx(h_out_W - h_in_W, rel=1e-9)


def test_stripping_steam_matches_the_reboiler_duty(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    assert res.info["reboiler_duty_W"] > 0.0
    assert res.info["stripping_steam_mol_s"] > 0.0
    # The steam rate is the duty over the latent heat of water at the reboiler
    # temperature; at 394 K that latent heat sits in a narrow published band.
    h_vap = res.info["reboiler_duty_W"] / res.info["stripping_steam_mol_s"]
    assert 3.5e4 < h_vap < 4.3e4
    assert 1.0 < res.info["steam_kg_per_kg_acid_gas"] < 100.0


def test_determinism(thermo: Thermo) -> None:
    first, _ = _solved(thermo)
    second, _ = _solved(thermo)
    assert first == second


def test_no_acid_gas_to_strip_raises(thermo: Thermo) -> None:
    """Lean targets above the rich loadings leave nothing to strip.

    Uses a lightly-loaded rich feed so the targets stay below the pressure
    ceiling (the example case's 0.40 CO2 loading would trip the ceiling check
    first).
    """
    unit = registry.create("unit", "mdea_regenerator")
    _, defaults = unit.example_case()
    rich = {
        "T": 303.15,
        "P": 1.8e5,
        "molar_flow": 300.0,
        "composition": {"MDEA": 0.124, "H2O": 0.87104, "CO2": 0.00372, "H2S": 0.00124},
    }
    inlets = {"rich_amine_in": flash_feed(thermo, rich)}
    # Pressure inside the boiling window at 394.15 K (x_H2O*Psat < P < Psat) so
    # the ceiling check passes and the no-strip branch is what raises.
    with pytest.raises(ValueError, match="no acid gas to strip"):
        unit.solve(
            inlets,
            {**defaults, "lean_co2_loading": 0.035, "lean_h2s_loading": 0.012, "regenerator_P": 1.95e5},
            thermo,
        )


def test_pressure_at_or_above_water_saturation_raises(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="saturation pressure"):
        _solved(thermo, {"regenerator_P": 3.0e5})


def test_infeasible_lean_ceiling_raises(thermo: Thermo) -> None:
    # Just below the water saturation point at 391 K: boiling passes but the
    # water vapor pressure over the solvent crowds out the acid-gas targets.
    with pytest.raises(ValueError, match="infeasible regeneration"):
        _solved(thermo, {"reboiler_T": 391.15, "regenerator_P": 1.5e5})


def test_negative_lean_target_raises(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _solved(thermo, {"lean_h2s_loading": -0.01})
