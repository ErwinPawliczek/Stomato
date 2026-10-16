"""Wiring tests: equilibrium_model selection in the amine units.

KE stays the default (the existing sour-gas suites are its regression
guard); ``enrtl`` is opt-in, CO2-only, MDEA/MEA. ``params`` is an opaque
dict on UnitSpec, so the field round-trips the API contract unchanged
(no OpenAPI change -- verified against contracts/plugins.py).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed


def _sweet_inlets(
    thermo: Thermo,
) -> tuple[dict[str, StreamState], dict[str, dict[str, Any]]]:
    """CO2-only case (no H2S in the gas or the lean solvent)."""
    unit = registry.create("unit", "mdea_absorber")
    feeds, _defaults = unit.example_case()
    feeds["gas_in"]["composition"] = {
        "C1": 0.91,
        "C2": 0.03,
        "N2": 0.0,
        "CO2": 0.06,
        "H2S": 0.0,
    }
    lean = feeds["lean_amine_in"]["composition"]
    lean_h2s = lean.pop("H2S", 0.0)
    if lean_h2s:
        # Redistribute the removed H2S onto the solvent so mole fractions sum to 1.
        lean["H2O"] = lean.get("H2O", 0.0) + lean_h2s
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}, feeds


def _solved(thermo: Thermo, params: dict[str, Any]) -> Any:
    unit = registry.create("unit", "mdea_absorber")
    inlets, _feeds = _sweet_inlets(thermo)
    return unit.solve(inlets, params, thermo)


def test_default_model_is_kent_eisenberg(thermo: Thermo) -> None:
    """Omitting the field must reproduce the explicit KE solve exactly."""
    unit = registry.create("unit", "mdea_absorber")
    inlets, _ = _sweet_inlets(thermo)
    default = unit.solve(inlets, {}, thermo)
    explicit = unit.solve(inlets, {"equilibrium_model": "kent_eisenberg"}, thermo)
    assert default.info == explicit.info


def test_enrtl_absorber_solves_and_is_deterministic(thermo: Thermo) -> None:
    res = _solved(thermo, {"equilibrium_model": "enrtl"})
    removed = res.info["co2_removed_mol_s"]
    assert removed > 0.0
    # Determinism: a byte-identical double-run reproduces the readouts.
    again = _solved(thermo, {"equilibrium_model": "enrtl"})
    assert again.info == res.info


def test_enrtl_dispatches_differently_than_ke(thermo: Thermo) -> None:
    """The models disagree on the equilibrium ceiling (the selector dispatches).

    removed_co2 is spec-driven and identical by construction; the
    bottom-stage equilibrium ceiling is a chemistry output.
    """
    ke = _solved(thermo, {"equilibrium_model": "kent_eisenberg"})
    en = _solved(thermo, {"equilibrium_model": "enrtl"})
    assert ke.info["equilibrium_max_co2_loading"] != pytest.approx(
        en.info["equilibrium_max_co2_loading"], rel=1e-9
    )


def test_enrtl_rejects_sour_service_in_the_unit(thermo: Thermo) -> None:
    """A sour feed must be refused on the e-NRTL path with the evidence error."""
    unit = registry.create("unit", "mdea_absorber")
    feeds, _defaults = unit.example_case()  # the example is sour (1.5% H2S)
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="H2S|electrolyte-NRTL"):
        unit.solve(inlets, {"equilibrium_model": "enrtl"}, thermo)


def test_unknown_model_name_is_rejected(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="equilibrium_model"):
        _solved(thermo, {"equilibrium_model": "pitzer"})


def test_enrtl_regenerator_solves_on_the_sweet_case(thermo: Thermo) -> None:
    """The regenerator accepts the field and dispatches to e-NRTL."""
    unit = registry.create("unit", "mdea_regenerator")
    feeds, _defaults = unit.example_case()
    # CO2-only case: strip H2S from every feed composition, redistributing
    # the mole fraction onto H2O so the fractions keep summing to 1.
    for feed in feeds.values():
        comp = feed.get("composition")
        if comp and "H2S" in comp:
            comp = dict(comp)
            h2s = comp.pop("H2S")
            comp["H2O"] = comp.get("H2O", 0.0) + h2s
            feed["composition"] = comp
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = unit.solve(inlets, {"equilibrium_model": "enrtl", "lean_h2s_loading": 0.0}, thermo)
    assert result.info["co2_stripped_mol_s"] > 0.0
