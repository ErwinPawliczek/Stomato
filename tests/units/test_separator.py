"""Spec S-24 acceptance tests: three-phase separator and scrubber."""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind, StreamState
from tests.conftest import flash_feed


@pytest.fixture(name="solved")
def _solved(thermo) -> dict[str, StreamState]:
    unit = registry.create("unit", "separator_3phase")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit.solve(inlets, params, thermo).outlets


def test_slice_inlet_gives_all_three_outlets(solved) -> None:
    for port in ("gas_out", "hc_out", "water_out"):
        assert solved[port].molar_flow > 0, f"{port} flow must be non-zero"


def test_gas_outlet_is_single_phase_vapor(solved) -> None:
    gas = solved["gas_out"]
    assert gas.vapor_fraction == pytest.approx(1.0)
    assert all(p.kind is PhaseKind.VAPOR for p in gas.phases)


def test_duty_is_near_zero_for_zero_dp(thermo) -> None:
    unit = registry.create("unit", "separator_3phase")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = unit.solve(inlets, params, thermo)
    scale = abs(inlets["inlet"].enthalpy * inlets["inlet"].molar_flow)
    assert abs(result.duty_W) < 1e-6 * scale


def test_scrubber_combines_liquids(thermo) -> None:
    unit = registry.create("unit", "scrubber")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    outlets = unit.solve(inlets, params, thermo).outlets
    assert set(outlets) == {"gas_out", "liquid_out"}
    assert outlets["gas_out"].molar_flow > 0
    assert outlets["liquid_out"].molar_flow > 0


def test_dp_lowers_outlet_pressure(thermo) -> None:
    unit = registry.create("unit", "separator_3phase")
    feeds, _params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    outlets = unit.solve(inlets, {"dP": 50e3}, thermo).outlets
    for state in outlets.values():
        assert state.T == pytest.approx(inlets["inlet"].T)
        assert state.P == pytest.approx(inlets["inlet"].P - 50e3)
