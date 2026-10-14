"""Tests for the TEG contactor unit (spec S-29)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from tests.conftest import flash_feed

#: Standard conditions volume basis, scf/lbmol (spec S-29).
SCF_PER_LBMOL = 379.49


def _water_content_lb_per_mmscf(y: float) -> float:
    """Inverse of the unit's GPSA water-content conversion, lb/MMscf."""
    mw = float(components()["H2O"]["mw"])
    return y / (1.0 - y) * mw * (1.0e6 / SCF_PER_LBMOL)


def _solved(thermo: Thermo, params: dict[str, Any] | None = None) -> Any:
    unit = registry.create("unit", "teg_contactor")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit.solve(inlets, params if params is not None else defaults, thermo), inlets


def test_registered() -> None:
    assert "teg_contactor" in registry.available("unit")


def test_ports(thermo: Thermo) -> None:
    unit = registry.create("unit", "teg_contactor")
    assert unit.inlet_ports == ("gas_in", "lean_teg_in")
    assert unit.outlet_ports == ("gas_out", "rich_teg_out")


def test_outlet_water_content_meets_spec(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    gas_out: StreamState = res.outlets["gas_out"]
    spec = res.info["outlet_water_lb_per_mmscf"]
    assert math.isclose(_water_content_lb_per_mmscf(gas_out.composition["H2O"]), spec, rel_tol=0.01)


def test_default_spec_is_7_lb_per_mmscf(thermo: Thermo) -> None:
    res, _ = _solved(thermo, {})
    assert res.info["outlet_water_lb_per_mmscf"] == pytest.approx(7.0)


def test_infeasible_spec_raises(thermo: Thermo) -> None:
    # 1000 lb/MMscf is far above the example inlet water content (~24 lb/MMscf).
    with pytest.raises(ValueError, match="infeasible spec"):
        _solved(thermo, {"water_out_lb_per_mmscf": 1000.0})


def test_nonpositive_spec_raises(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="positive"):
        _solved(thermo, {"water_out_lb_per_mmscf": 0.0})


def test_water_moves_to_rich_teg(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    gas_in, teg_in = inlets["gas_in"], inlets["lean_teg_in"]
    gas_out = res.outlets["gas_out"]
    rich_out = res.outlets["rich_teg_out"]

    lost_by_gas = gas_in.composition["H2O"] * gas_in.molar_flow - (
        gas_out.composition["H2O"] * gas_out.molar_flow
    )
    gained_by_teg = rich_out.composition["H2O"] * rich_out.molar_flow - (
        teg_in.composition["H2O"] * teg_in.molar_flow
    )
    assert gained_by_teg == pytest.approx(lost_by_gas, rel=1e-9)

    removed_kg_h = res.info["water_removed_kg_h"]
    mw = float(components()["H2O"]["mw"])
    assert removed_kg_h == pytest.approx(lost_by_gas * mw / 1000.0 * 3600.0, rel=1e-9)
    assert removed_kg_h > 0.0


def test_non_water_components_unchanged_in_gas(thermo: Thermo) -> None:
    res, inlets = _solved(thermo)
    gas_in, gas_out = inlets["gas_in"], res.outlets["gas_out"]
    for comp, frac_in in gas_in.composition.items():
        if comp == "H2O":
            continue
        flow_out = gas_out.composition.get(comp, 0.0) * gas_out.molar_flow
        assert flow_out == pytest.approx(frac_in * gas_in.molar_flow, rel=1e-9)


def test_stages_and_circulation_reported(thermo: Thermo) -> None:
    res, _ = _solved(thermo)
    assert res.info["N_stages"] > 0.0
    assert res.info["teg_circulation_L_per_kg_water"] > 0.0
