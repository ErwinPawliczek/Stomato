"""Spec U-E acceptance: shortcut-cascade physics — Fenske/Underwood/Gilliland/
Kirkbride and the Kremser group method, against hand-computed values.

The pure functions are tested on constant relative volatility cases where the
closed forms have exact analytic answers (theta = 4/3 at q = 1, sqrt(2) at
q = 0.5, 6/7 extraction at A = 2, N = 2, ...); the adapter-level reference
behaviour is pinned by the V1 cases in data/validation_units/column/cases.yaml
against the printed tables of Seader, Henley & Roper, 3rd ed.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units._physics.shortcut import (
    fenske_nmin,
    gilliland,
    kirkbride,
    kremser_fraction,
    kremser_stage_count,
    underwood_rmin,
    underwood_theta,
)
from ngdesign.units.column_shortcut._kremser import two_feed_split

# ---------------------------------------------------------------------------
# Fenske


def test_fenske_nmin_symmetric_binary() -> None:
    # alpha = 2, xD = (0.9, 0.1), xB = (0.1, 0.9): Nmin = log(81)/log(2).
    assert fenske_nmin(2.0, 0.9, 0.1, 0.1, 0.9) == pytest.approx(math.log(81.0) / math.log(2.0))


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ((0.0, 0.9, 0.1, 0.1, 0.9), "must be positive"),
        ((1.0, 0.9, 0.1, 0.1, 0.9), "must differ from 1"),
        ((2.0, 0.9, 0.0, 0.1, 0.9), "xD_HK must be positive"),
        ((2.0, 0.9, 0.1, 0.0, 0.9), "xB_LK must be positive"),
    ],
)
def test_fenske_nmin_refuses_nonphysical(args: tuple[float, ...], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        fenske_nmin(*args)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Underwood root, binary constant-alpha analytic cases.
# For alphas (2, 1) and z = (0.5, 0.5) the root solves
# 1/(2 - theta) + 0.5/(1 - theta) = 1 - q exactly.


def test_underwood_theta_saturated_liquid() -> None:
    theta = underwood_theta({"LK": 2.0, "HK": 1.0}, {"LK": 0.5, "HK": 0.5}, 1.0)
    assert theta == pytest.approx(4.0 / 3.0)


def test_underwood_theta_saturated_vapour() -> None:
    theta = underwood_theta({"LK": 2.0, "HK": 1.0}, {"LK": 0.5, "HK": 0.5}, 0.0)
    assert theta == pytest.approx(1.5)


def test_underwood_theta_half_quality() -> None:
    theta = underwood_theta({"LK": 2.0, "HK": 1.0}, {"LK": 0.5, "HK": 0.5}, 0.5)
    assert theta == pytest.approx(math.sqrt(2.0))


def test_underwood_theta_unbracketed_without_heavy_key() -> None:
    # No heavy-key term means f(1+) is positive; the Class-2 root does not exist.
    with pytest.raises(ValueError, match="not bracketed"):
        underwood_theta({"LK": 2.0, "HK": 1.0}, {"LK": 1.0, "HK": 0.0}, 1.0)


def test_underwood_theta_refuses_bad_inputs() -> None:
    with pytest.raises(ValueError, match="must exceed 1"):
        underwood_theta({"LK": 1.0, "HK": 0.9}, {"LK": 0.5, "HK": 0.5}, 1.0)
    with pytest.raises(ValueError, match="must lie in"):
        underwood_theta({"LK": 2.0, "HK": 1.0}, {"LK": 0.5, "HK": 0.5}, 1.5)


def test_underwood_rmin_binary() -> None:
    # theta = 4/3, xD = (0.9, 0.1): Rmin + 1 = 1.8/(2/3) - 0.1/(1/3) = 2.4.
    rmin = underwood_rmin({"LK": 2.0, "HK": 1.0}, {"LK": 0.9, "HK": 0.1}, 4.0 / 3.0)
    assert rmin == pytest.approx(1.4)


def test_underwood_rmin_singularity() -> None:
    with pytest.raises(ValueError, match="singularity"):
        underwood_rmin({"LK": 2.0, "HK": 1.0}, {"LK": 0.9, "HK": 0.1}, 2.0)


# ---------------------------------------------------------------------------
# Gilliland (Molokanov form).


def test_gilliland_infinite_reflux_recovers_nmin() -> None:
    assert gilliland(1e9, 1.0, 10.0) == pytest.approx(10.0, rel=1e-6)


def test_gilliland_hand_point() -> None:
    # R = 2, Rmin = 1, Nmin = 5: X = 1/3, Y = 0.356766..., N = 8.3280...
    r = gilliland(2.0, 1.0, 5.0)
    assert r == pytest.approx(8.3280, rel=1e-3)


@pytest.mark.parametrize("args", [(-1.0, 1.0, 5.0), (1.0, 2.0, 5.0), (2.0, 1.0, 0.0)])
def test_gilliland_refuses_infeasible(args: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        gilliland(*args)


# ---------------------------------------------------------------------------
# Kirkbride.


def test_kirkbride_symmetric_is_unity() -> None:
    assert kirkbride(0.5, 0.5, 0.5, 0.5, 1.0) == pytest.approx(1.0)


def test_kirkbride_exponent() -> None:
    base = (0.4 / 0.6) * (0.2 / 0.1) ** 2 * 1.5
    assert kirkbride(0.4, 0.6, 0.2, 0.1, 1.5) == pytest.approx(base**0.206)


def test_kirkbride_refuses_nonpositive() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        kirkbride(0.4, 0.6, 0.0, 0.1, 1.5)


# ---------------------------------------------------------------------------
# Kremser.


def test_kremser_fraction_hand_values() -> None:
    assert kremser_fraction(2.0, 2.0) == pytest.approx(6.0 / 7.0)
    assert kremser_fraction(3.0, 1.0) == pytest.approx((9.0 - 3.0) / (9.0 - 1.0))


def test_kremser_fraction_unit_factor_limit() -> None:
    # The A -> 1 limit is N/(N+1): 2/3 at two stages.
    assert kremser_fraction(1.0, 2.0) == pytest.approx(2.0 / 3.0)


def test_kremser_fraction_zero_stages() -> None:
    assert kremser_fraction(2.0, 0.0) == pytest.approx(0.0)


def test_kremser_fraction_saturates_at_one() -> None:
    assert kremser_fraction(50.0, 20.0) == pytest.approx(1.0)


def test_kremser_fraction_refuses_bad_inputs() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        kremser_fraction(0.0, 2.0)
    with pytest.raises(ValueError, match="must be non-negative"):
        kremser_fraction(1.0, -1.0)


def test_kremser_stage_count_round_trip() -> None:
    for a, n in ((0.5, 3.0), (2.0, 2.0), (1.0, 4.0), (0.031, 6.0)):
        phi = kremser_fraction(a, n)
        assert kremser_stage_count(a, phi) == pytest.approx(n, rel=1e-8)


def test_kremser_absorber_book_example_53() -> None:
    # Example 5.3, p. 188: fA = 1 - kremser_fraction(A, 6) reproduces the
    # printed table (C1 0.969 at A = 0.031; nC4 0.119 at A = 1.06).
    assert 1.0 - kremser_fraction(0.0310, 6.0) == pytest.approx(0.969, abs=5e-4)
    assert 1.0 - kremser_fraction(1.06, 6.0) == pytest.approx(0.119, abs=1e-3)


def test_kremser_extractor_book_example_52() -> None:
    # Example 5.2: E = 2.4 gives 89.1 % at two stages and 99.26 % at five.
    assert kremser_fraction(2.4, 2.0) == pytest.approx(0.8908, abs=5e-4)
    assert kremser_fraction(2.4, 5.0) == pytest.approx(0.9926, abs=5e-4)


# ---------------------------------------------------------------------------
# Two-feed Kremser split (the absorber/extractor engine) on the Example 5.2
# basis converted to moles: K_D = 5.2027, S/F = 87.085/188.840, E = 2.3992.


def test_two_feed_split_extractor_example() -> None:
    extract, raffinate = two_feed_split(
        {}, {"p-dioxane": 12.871}, {"p-dioxane": 5.2027}, 188.840, 87.085, 2.0
    )
    assert extract["p-dioxane"] == pytest.approx(11.4652, rel=1e-4)
    assert raffinate["p-dioxane"] == pytest.approx(1.4058, rel=1e-3)
    # Book's 89.1 % extraction.
    assert extract["p-dioxane"] / 12.871 == pytest.approx(0.8908, abs=5e-4)


def test_two_feed_split_preserves_total() -> None:
    # Every component splits through its own factor; a tiny K pins a
    # non-absorbed carrier to the liquid side (the oil stand-in in Ex. 5.3).
    solvent_side = {"C6+": 5.0}
    feed_side = {"A": 8.0, "B": 2.0}
    k_map = {"A": 2.0, "B": 0.5, "C6+": 1e-4}
    extract, raffinate = two_feed_split(solvent_side, feed_side, k_map, 100.0, 40.0, 5.0)
    for cid, flow in {**solvent_side, **feed_side}.items():
        assert extract.get(cid, 0.0) + raffinate.get(cid, 0.0) == pytest.approx(flow)
    assert extract["C6+"] == pytest.approx(0.0, abs=1e-6)
    assert raffinate["C6+"] == pytest.approx(5.0)
