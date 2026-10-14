"""Tests for the ASME B16.5 flange rating correlation (spec S-11)."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.sizing.flange_rating import flange_rating_b165, min_flange_class


def test_hand_checked_interpolation() -> None:
    """Hand check: 1.1 class 300 between 200 F (680) and 300 F (655) at 250 F -> 667.5."""
    assert math.isclose(flange_rating_b165("1.1", 300, 250.0), 667.5, rel_tol=1e-9)


def test_at_table_temperatures_exact() -> None:
    assert math.isclose(flange_rating_b165("1.1", 150, 100.0), 285.0, rel_tol=1e-9)
    assert math.isclose(flange_rating_b165("2.2", 300, 100.0), 720.0, rel_tol=1e-9)


def test_below_lowest_temperature_uses_100f_value() -> None:
    assert math.isclose(flange_rating_b165("1.1", 150, -20.0), 285.0, rel_tol=1e-9)
    assert math.isclose(flange_rating_b165("2.2", 300, -50.0), 720.0, rel_tol=1e-9)


def test_above_table_range_raises_value_error() -> None:
    with pytest.raises(ValueError, match="above B16.5 table range"):
        flange_rating_b165("1.1", 150, 750.0)


def test_unknown_material_group_or_class_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no B16.5 rating rows"):
        flange_rating_b165("9.9", 150, 100.0)
    with pytest.raises(ValueError, match="no B16.5 rating rows"):
        flange_rating_b165("1.1", 9000, 100.0)


def test_min_flange_class_hand_checked() -> None:
    """285 psig at 100 F: class 150 is rated exactly 285, so it suffices."""
    assert min_flange_class("1.1", 285.0, 100.0) == 150
    """286 psig at 100 F exceeds class 150; class 300 (740) is next."""
    assert min_flange_class("1.1", 286.0, 100.0) == 300
    """Class 900 (2220 psig at 100 F) is the last resort on file."""
    assert min_flange_class("1.1", 2220.0, 100.0) == 900


def test_min_flange_class_invalid_inputs_raise_value_error() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        min_flange_class("1.1", 0.0, 100.0)
    with pytest.raises(ValueError, match="must be positive"):
        min_flange_class("1.1", -100.0, 100.0)
    with pytest.raises(ValueError, match="unknown material group"):
        min_flange_class("9.9", 100.0, 100.0)
    with pytest.raises(ValueError, match="above B16.5 table range"):
        min_flange_class("1.1", 100.0, 800.0)
    with pytest.raises(ValueError, match="no B16.5 class"):
        min_flange_class("1.1", 99999.0, 100.0)


def test_correlation_plugin_registered() -> None:
    """The registered correlation plugin returns the expected key."""
    plugin = registry.create("correlation", "flange_rating_b165")
    got = plugin(material_group="1.1", flange_class=300, temp_F=250.0)
    assert set(got) == {"max_pressure_psig"}
    assert math.isclose(got["max_pressure_psig"], 667.5, rel_tol=1e-9)
