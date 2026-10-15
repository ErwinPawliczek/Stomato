"""Tests for the ASME B31.3 wall thickness correlation (spec S-02)."""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ngdesign import registry
from ngdesign.sizing.wall_thickness import select_schedule, wall_thickness_b313

CASE_1: dict[str, Any] = {
    "nps_in": 6,
    "design_pressure_gauge_Pa": 5_000_000.0,
    "pipe_class": "B1",
    "allowable_stress_MPa": 137.9,
    "E": 1.0,
    "W": 1.0,
    "Y": 0.4,
    "corrosion_allowance_mm": 3.0,
    "mill_tolerance": 0.125,
}


def test_hand_checked_nps6_5mpa() -> None:
    """Hand check: t = 5*168.3/(2*(137.9 + 5*0.4)) = 3.0075 mm; nominal 6.8657 -> SCH 40."""
    got = wall_thickness_b313(**CASE_1)
    assert math.isclose(cast(float, got["od_mm"]), 168.3, rel_tol=1e-12)
    assert math.isclose(cast(float, got["t_pressure_mm"]), 3.0075, rel_tol=1e-4)
    assert math.isclose(cast(float, got["t_required_nominal_mm"]), 6.8657, rel_tol=1e-4)
    assert math.isclose(cast(float, got["selected_wall_mm"]), 7.11, rel_tol=1e-12)
    assert got["selected_schedule"] == "40"


def test_select_schedule_reads_pipe_class_data() -> None:
    """Class B1 carries the same S/E/W/Y/CA as the hand-checked case."""
    assert select_schedule(6, 5_000_000.0, "B1")["selected_schedule"] == "40"


def test_select_schedule_unknown_class_raises() -> None:
    with pytest.raises(ValueError, match="unknown pipe class"):
        select_schedule(6, 5_000_000.0, "NOPE")


@pytest.mark.parametrize(
    "override",
    [
        {"nps_in": 0},
        {"nps_in": -2},
        {"design_pressure_gauge_Pa": 0.0},
        {"design_pressure_gauge_Pa": -1.0},
        {"allowable_stress_MPa": 0.0},
        {"allowable_stress_MPa": -137.9},
        {"E": 0.0},
        {"W": -1.0},
        {"Y": -0.4},
        {"corrosion_allowance_mm": -0.1},
        {"mill_tolerance": -0.01},
        {"mill_tolerance": 1.0},
        {"pipe_class": "NOPE"},
    ],
)
def test_invalid_input_raises_value_error(override: dict[str, Any]) -> None:
    kwargs = {**CASE_1, **override}
    with pytest.raises(ValueError):
        wall_thickness_b313(**kwargs)


def test_unknown_nps_raises_value_error() -> None:
    kwargs = {**CASE_1, "nps_in": 6.3}
    with pytest.raises(ValueError, match="unknown NPS"):
        wall_thickness_b313(**kwargs)


def test_no_sufficient_schedule_raises_value_error() -> None:
    """Pressure far beyond XXS capacity must report no schedule, not fail arithmetic."""
    kwargs = {**CASE_1, "design_pressure_gauge_Pa": 500_000_000.0}
    with pytest.raises(ValueError, match="no schedule"):
        wall_thickness_b313(**kwargs)


def test_correlation_plugin_registered_and_matches_golden_shape() -> None:
    """The registered correlation plugin returns every expected key."""
    plugin = registry.create("correlation", "wall_thickness_b313")
    got = plugin(**CASE_1)
    assert set(got) == {
        "od_mm",
        "t_pressure_mm",
        "t_required_nominal_mm",
        "selected_wall_mm",
        "selected_schedule",
    }
