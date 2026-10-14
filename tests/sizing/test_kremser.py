"""Tests for the Kremser absorber correlation (spec S-05)."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.sizing.kremser import kremser


def test_hand_checked_case() -> None:
    """A=1.4, y_in=900, y_out=90, m=150, x_top=0.1: R=11.8, N = ln(R*(1-1/A)+1/A)/ln(A)."""
    got = kremser(A=1.4, y_in=900, y_out=90, m=150, x_top=0.1)
    assert math.isclose(got["N_stages"], 4.1830986797136465, rel_tol=1e-12)


def test_a_equals_one_limit() -> None:
    """At A = 1 the limit form gives N = (y_in - y_out)/(y_out - m*x_top) = 800/180."""
    got = kremser(A=1.0, y_in=1000, y_out=200, m=100, x_top=0.2)
    assert math.isclose(got["N_stages"], 4.444444444444445, rel_tol=1e-12)


def test_first_golden_case() -> None:
    """Inputs of data/golden/kremser.yaml case 0, expected value from the file."""
    got = kremser(A=1.5, y_in=2000, y_out=150, m=100, x_top=0.5)
    assert math.isclose(got["N_stages"], 4.857238, rel_tol=1e-6)


def test_more_stages_for_leaner_solvent() -> None:
    """Raising x_top toward m*x_top = y_out must increase N (harder spec)."""
    base = kremser(A=1.5, y_in=2000, y_out=150, m=100, x_top=0.5)["N_stages"]
    harder = kremser(A=1.5, y_in=2000, y_out=150, m=100, x_top=0.9)["N_stages"]
    assert harder > base


@pytest.mark.parametrize(
    "kwargs",
    [
        {"A": 0.0, "y_in": 2000, "y_out": 150, "m": 100, "x_top": 0.5},
        {"A": -1.5, "y_in": 2000, "y_out": 150, "m": 100, "x_top": 0.5},
        {"A": 1.5, "y_in": 2000, "y_out": 150, "m": 0, "x_top": 0.5},
        {"A": 1.5, "y_in": 2000, "y_out": 150, "m": 100, "x_top": -0.5},
        {"A": 1.5, "y_in": -2000, "y_out": 150, "m": 100, "x_top": 0.5},
        {"A": 1.5, "y_in": 2000, "y_out": -150, "m": 100, "x_top": 0.5},
        # Infeasible: y_out <= m*x_top.
        {"A": 1.5, "y_in": 2000, "y_out": 50, "m": 100, "x_top": 0.5},
        {"A": 1.5, "y_in": 2000, "y_out": 150, "m": 100, "x_top": 2.0},
        # Infeasible: y_in < y_out.
        {"A": 1.5, "y_in": 100, "y_out": 150, "m": 100, "x_top": 0.5},
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        kremser(**kwargs)


def test_plugin_registered() -> None:
    """The plugin is discoverable and reproduces the golden-file inputs."""
    assert "kremser" in registry.available("correlation")
    plugin = registry.create("correlation", "kremser")
    got = plugin(**{"A": 1.5, "y_in": 2000, "y_out": 150, "m": 100, "x_top": 0.5})
    assert math.isclose(got["N_stages"], 4.857238, rel_tol=1e-6)
