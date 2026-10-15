"""Spec S-25 acceptance tests: compressor with isentropic efficiency."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed


def _solve(thermo: Thermo, params: dict[str, Any]) -> UnitResult:
    unit = registry.create("unit", "compressor")
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result: UnitResult = unit.solve(inlets, params, thermo)
    return result


def test_eta_one_reproduces_isentropic_outlet_temperature(thermo: Thermo) -> None:
    unit = registry.create("unit", "compressor")
    _feeds, params = unit.example_case()
    result = _solve(thermo, {**params, "eta_isentropic": 1.0})
    assert result.outlets["outlet"].T == pytest.approx(result.info["T_out_isentropic"], rel=1e-6)


def test_lower_eta_gives_higher_outlet_temperature_and_power(thermo: Thermo) -> None:
    unit = registry.create("unit", "compressor")
    _feeds, params = unit.example_case()
    best = _solve(thermo, {**params, "eta_isentropic": 0.90})
    worst = _solve(thermo, {**params, "eta_isentropic": 0.60})
    t_best = best.outlets["outlet"].T
    t_worst = worst.outlets["outlet"].T
    assert t_worst > t_best
    assert worst.power_W > best.power_W


def test_rejects_liquid_inlet(thermo: Thermo) -> None:
    unit = registry.create("unit", "compressor")
    feeds, params = unit.example_case()
    feeds["inlet"]["T"] = 293.15  # the dry gas is two-phase here (vf ~ 0.99)
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="liquid"):
        unit.solve(inlets, params, thermo)


def test_rejects_pressure_letdown(thermo: Thermo) -> None:
    _feeds, params = registry.create("unit", "compressor").example_case()
    with pytest.raises(ValueError, match="P_out"):
        _solve(thermo, {**params, "P_out": 1.0e6})
