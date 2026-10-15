"""Spec S-26 acceptance tests: heater, cooler, air cooler, shell-and-tube."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo, UnitModel
from tests.conftest import flash_feed

NAMES = ("heater", "cooler", "air_cooler", "shell_tube")


def _solve(thermo: Thermo, name: str, params: dict[str, Any]) -> tuple[UnitModel, UnitResult]:
    unit = registry.create("unit", name)
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return unit, unit.solve(inlets, params, thermo)


@pytest.mark.parametrize("name", NAMES)
def test_cooling_gives_negative_duty(thermo: Thermo, name: str) -> None:
    _unit, result = _solve(thermo, name, {"T_out": 313.15, "dP": 35e3})
    assert result.duty_W < 0
    assert result.info["duty_kW"] == pytest.approx(result.duty_W / 1000.0)


@pytest.mark.parametrize("name", NAMES)
def test_duty_spec_and_tout_spec_agree(thermo: Thermo, name: str) -> None:
    """T_out spec -> duty; feed that duty back -> same outlet state."""
    unit = registry.create("unit", name)
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    by_T = unit.solve(inlets, defaults, thermo)
    duty = by_T.duty_W

    by_duty = unit.solve(inlets, {"duty_W": duty, "dP": defaults["dP"]}, thermo)
    t_out = by_duty.outlets["outlet"].T
    t_target = by_T.outlets["outlet"].T
    assert t_out == pytest.approx(t_target, abs=0.5)  # 0.5 K round-trip
    assert by_duty.duty_W == pytest.approx(duty, rel=1e-3)


def test_requires_exactly_one_spec(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        _solve(thermo, "heater", {})
    with pytest.raises(ValueError, match="exactly one"):
        _solve(thermo, "heater", {"T_out": 313.15, "duty_W": -1e6})


def test_dp_lowers_outlet_pressure(thermo: Thermo) -> None:
    unit = registry.create("unit", "cooler")
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    outlet = unit.solve(inlets, {"T_out": 313.15, "dP": 35e3}, thermo).outlets["outlet"]
    assert outlet.P == pytest.approx(inlets["inlet"].P - 35e3)
