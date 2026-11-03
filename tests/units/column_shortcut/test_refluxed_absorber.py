"""Refluxed / reboiled absorber R2: reduction to the zero-tear absorber, stage audit.

The independent checks: every stage closes when recomputed from the reported
profile (tests/units/column/stage_audit.py), and the one-exchanger column must
REDUCE to the zero-tear absorber R2 when its exchanger has nothing to do. A
partial condenser whose vapour product equals the absorber's top vapour has no
reason to condense anything; a kettle whose boilup equals the absorber's bottom
vapour has nothing to boil.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column_shortcut.refluxed_absorber import RefluxedAbsorber, RefluxedAbsorberError
from tests.conftest import flash_feed
from tests.units.column.stage_audit import (
    energy_residuals,
    equilibrium_residuals,
    material_residuals,
    read_stages,
)

COMPS = ["C2", "C3", "NC4"]


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = RefluxedAbsorber.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def test_refluxed_stage_audit(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    _, params = RefluxedAbsorber.example_case()
    res = RefluxedAbsorber().solve(inlets, params, thermo)
    stages = read_stages(res.info, COMPS)
    feeds = {7: [inlets["gas_in"]], 2: [inlets["solvent_in"]]}
    assert max(material_residuals(stages, COMPS, feeds)) < 1e-6
    # Stage 1 is the condenser: its balance defines the duty.
    assert max(energy_residuals(thermo, stages, feeds, skip=frozenset({0}))) < 1e-3
    assert max(equilibrium_residuals(thermo, stages)) < 1e-3
    assert res.outlets["gas_out"].molar_flow == pytest.approx(60.0, rel=5e-3)
    assert res.info["condenser_duty_W"] > 0.0
    assert res.outlets["gas_out"].vapor_fraction == pytest.approx(1.0, abs=1e-6)


def _absorber_basis(thermo: Thermo) -> dict[str, Any]:
    feeds = {
        "gas_in": {"T": 320.0, "P": 2.0e6, "molar_flow": 100.0, "composition": {"C2": 0.6, "C3": 0.4}},
        "solvent_in": {"T": 300.0, "P": 2.0e6, "molar_flow": 60.0, "composition": {"NC4": 1.0}},
    }
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _assert_same_profile(a: dict[str, float], b: dict[str, float], n: int) -> None:
    for j in range(n):
        assert a[f"stage_{j}_T_K"] == pytest.approx(b[f"stage_{j}_T_K"], abs=0.05), j
        assert a[f"stage_{j}_L_mol_s"] == pytest.approx(b[f"stage_{j}_L_mol_s"], rel=2e-3), j
        assert a[f"stage_{j}_x_C2"] == pytest.approx(b[f"stage_{j}_x_C2"], rel=2e-3), j


def test_refluxed_reduces_to_absorber_at_zero_condenser_duty(thermo: Thermo) -> None:
    """Vapour product = the zero-tear absorber's top vapour: the condenser idles."""
    inlets = _absorber_basis(thermo)
    plain = registry.create("unit", "absorber").solve(inlets, {"model": "R2", "n_stages": 6}, thermo)
    res = RefluxedAbsorber().solve(
        inlets,
        {
            "configuration": "refluxed",
            "n_stages": 6,
            "solvent_stage": 1,
            "spec": {"distillate_rate": plain.outlets["gas_out"].molar_flow},
        },
        thermo,
    )
    _assert_same_profile(res.info, plain.info, 6)
    throughput = abs(inlets["gas_in"].enthalpy * 100.0) + abs(inlets["solvent_in"].enthalpy * 60.0)
    assert res.info["condenser_duty_W"] < 1e-3 * throughput


@pytest.mark.timeout(300)  # measured 81 s: the boilup spec walks a narrow one-tear basin
def test_reboiled_reduces_to_absorber_at_zero_kettle_duty(thermo: Thermo) -> None:
    """Gas on the kettle stage, boilup = the absorber's bottom vapour: the kettle idles."""
    inlets = _absorber_basis(thermo)
    plain = registry.create("unit", "absorber").solve(inlets, {"model": "R2", "n_stages": 6}, thermo)
    ratio = plain.info["stage_5_V_mol_s"] / plain.outlets["rich_out"].molar_flow
    res = RefluxedAbsorber().solve(
        inlets,
        {"configuration": "reboiled", "n_stages": 6, "gas_stage": 6, "spec": {"boilup_ratio": ratio}},
        thermo,
    )
    _assert_same_profile(res.info, plain.info, 6)
    throughput = abs(inlets["gas_in"].enthalpy * 100.0) + abs(inlets["solvent_in"].enthalpy * 60.0)
    assert abs(res.info["reboiler_duty_W"]) < 1e-3 * throughput


def test_reboiled_configuration(thermo: Thermo) -> None:
    feeds = {
        "gas_in": {"T": 300.0, "P": 2.0e6, "molar_flow": 100.0, "composition": {"C1": 0.9, "NC4": 0.1}},
        "solvent_in": {"T": 300.0, "P": 2.0e6, "molar_flow": 30.0, "composition": {"NC4": 1.0}},
    }
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    res = RefluxedAbsorber().solve(
        inlets, {"configuration": "reboiled", "n_stages": 8, "spec": {"boilup_ratio": 0.2}}, thermo
    )
    comps = ["C1", "NC4"]
    stages = read_stages(res.info, comps)
    audit_feeds = {3: [inlets["gas_in"]], 0: [inlets["solvent_in"]]}
    assert max(material_residuals(stages, comps, audit_feeds)) < 1e-6
    assert max(energy_residuals(thermo, stages, audit_feeds, skip=frozenset({7}))) < 1e-3
    assert res.info["boilup_ratio"] == pytest.approx(0.2, rel=5e-3)
    assert res.info["reboiler_duty_W"] > 0.0
    # What the kettle is for: it boils methane back out of the rich liquid, so
    # the rich solvent carries less C1 than the unboiled absorber's.
    plain = registry.create("unit", "absorber").solve(inlets, {"model": "R2", "n_stages": 8}, thermo)
    assert res.outlets["rich_out"].composition["C1"] < plain.outlets["rich_out"].composition["C1"]
    assert res.outlets["gas_out"].molar_flow + res.outlets["rich_out"].molar_flow == pytest.approx(130.0)


@pytest.mark.parametrize(
    "params",
    [
        {"configuration": "sideways", "n_stages": 6, "spec": {"distillate_rate": 60.0}},
        {"configuration": "refluxed", "n_stages": 2, "spec": {"distillate_rate": 60.0}},
        {"configuration": "refluxed", "n_stages": 6, "spec": {"reflux_ratio": 2.0}},
        {"configuration": "reboiled", "n_stages": 6, "spec": {"distillate_rate": 60.0}},
        {"configuration": "reboiled", "n_stages": 6, "spec": {}},
        {"configuration": "refluxed", "n_stages": 6, "spec": {"distillate_rate": 60.0}, "x": 1},
        {
            "configuration": "reboiled",
            "n_stages": 6,
            "gas_stage": 2,
            "solvent_stage": 4,
            "spec": {"boilup_ratio": 1.0},
        },
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any]) -> None:
    with pytest.raises(RefluxedAbsorberError):
        RefluxedAbsorber().solve(_inlets(thermo), params, thermo)
