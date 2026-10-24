"""Closed-form tests for the shared split helper (spec U-A step 1).

The split arithmetic is hand-computed; the real ``pr`` package provides the
flashes (at a specified T and P the returned outlet state is exact by
construction, so every assertion below is closed-form, not fitted).
"""

from __future__ import annotations

import math
from typing import cast

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.splitting import SplittingError, split_by_component

FEED = StreamState(
    T=300.0,
    P=5.0e5,
    molar_flow=100.0,
    composition={"C1": 0.6, "nC4": 0.4},
    vapor_fraction=1.0,
    enthalpy=0.0,
    entropy=0.0,
)


@pytest.fixture(name="thermo")
def thermo_fixture() -> Thermo:
    return cast(Thermo, registry.create("thermo", "pr"))


def _feed_with_h(thermo: Thermo) -> StreamState:
    """The FEED flashed, so its enthalpy is the package's own (duty identity)."""
    return thermo.flash_pt(dict(FEED.composition), FEED.T, FEED.P, FEED.molar_flow)


def test_split_arithmetic_hand_computed(thermo: Thermo) -> None:
    """C1 half to top: top 30 mol/s pure C1, bottom 70 mol/s at 3/7 : 4/7."""
    feed = _feed_with_h(thermo)
    top, bottom = split_by_component(feed, {"C1": 0.5}, thermo)
    assert math.isclose(top.molar_flow, 30.0, rel_tol=1e-12)
    assert math.isclose(bottom.molar_flow, 70.0, rel_tol=1e-12)
    assert top.composition["C1"] == pytest.approx(1.0, abs=1e-12)
    assert bottom.composition["C1"] == pytest.approx(30.0 / 70.0, rel=1e-12)
    assert bottom.composition["nC4"] == pytest.approx(40.0 / 70.0, rel=1e-12)
    # both outlets default to the inlet's conditions
    assert top.T == feed.T and top.P == feed.P
    assert bottom.T == feed.T and bottom.P == feed.P


def test_missing_components_go_bottom(thermo: Thermo) -> None:
    """An empty fraction map sends everything to the bottom outlet."""
    feed = _feed_with_h(thermo)
    top, bottom = split_by_component(feed, {}, thermo)
    assert top.molar_flow == 0.0
    assert math.isclose(bottom.molar_flow, 100.0, rel_tol=1e-12)
    assert bottom.composition == pytest.approx(feed.composition)


def test_full_split_leaves_bottom_empty(thermo: Thermo) -> None:
    """All components at fraction 1: bottom is zero-flow, top is the feed."""
    feed = _feed_with_h(thermo)
    top, bottom = split_by_component(feed, {"C1": 1.0, "nC4": 1.0}, thermo)
    assert bottom.molar_flow == 0.0
    assert math.isclose(top.molar_flow, 100.0, rel_tol=1e-12)


def test_full_split_has_no_rounding_residue(thermo: Thermo) -> None:
    """3 mol/s at 0.05/0.25/0.7: 3 - sum(z*3) is 4.4e-16, not 0, in floating point.

    Every component to the top must still leave the bottom exactly empty
    (zero-flow at the requested conditions), not a residue flashed with an
    all-zero composition.
    """
    z = {"C1": 0.05, "C2": 0.25, "nC4": 0.7}
    assert 3.0 - sum(x * 3.0 for x in z.values()) > 0.0  # the residue the helper must avoid
    feed = thermo.flash_pt(z, 300.0, 5.0e5, 3.0)
    top, bottom = split_by_component(feed, dict.fromkeys(z, 1.0), thermo, outlet_T={"bottom": 280.0})
    assert bottom.molar_flow == 0.0
    assert bottom.T == 280.0
    assert top.molar_flow == pytest.approx(3.0, rel=1e-15)


def test_per_outlet_conditions(thermo: Thermo) -> None:
    """Each outlet flashes at its own (T, P); a scalar applies to both."""
    feed = _feed_with_h(thermo)
    top, bottom = split_by_component(
        feed,
        {"C1": 0.5},
        thermo,
        outlet_T={"top": 350.0, "bottom": 290.0},
        outlet_P={"top": 6.0e5, "bottom": 4.0e5},
    )
    assert top.T == 350.0 and top.P == 6.0e5
    assert bottom.T == 290.0 and bottom.P == 4.0e5
    scalar_top, scalar_bottom = split_by_component(feed, {"C1": 0.5}, thermo, outlet_T=325.0)
    assert scalar_top.T == 325.0 and scalar_bottom.T == 325.0


def test_duty_identity(thermo: Thermo) -> None:
    """The unit duty is sum(n*h) over outlets minus n_in*h_in, on flash enthalpies."""
    feed = _feed_with_h(thermo)
    top, bottom = split_by_component(feed, {"C1": 0.5}, thermo)
    duty = (
        top.molar_flow * top.enthalpy + bottom.molar_flow * bottom.enthalpy - feed.molar_flow * feed.enthalpy
    )
    # an isothermal, isobaric split of an ideal-slate feed has a small but
    # finite mixing duty; the check is that the identity evaluates, and that a
    # full-to-top split reports exactly zero (no flash change anywhere).
    assert math.isfinite(duty)
    top_full, bottom_full = split_by_component(feed, {"C1": 1.0, "nC4": 1.0}, thermo)
    duty_full = (
        top_full.molar_flow * top_full.enthalpy
        + bottom_full.molar_flow * bottom_full.enthalpy
        - feed.molar_flow * feed.enthalpy
    )
    assert duty_full == pytest.approx(0.0, abs=1e-6)


def test_refuses_out_of_range_fraction(thermo: Thermo) -> None:
    feed = _feed_with_h(thermo)
    with pytest.raises(SplittingError, match="C1"):
        split_by_component(feed, {"C1": 1.5}, thermo)


def test_refuses_unknown_component(thermo: Thermo) -> None:
    feed = _feed_with_h(thermo)
    with pytest.raises(SplittingError, match="H2S"):
        split_by_component(feed, {"H2S": 0.5}, thermo)


def test_refuses_nonpositive_conditions(thermo: Thermo) -> None:
    feed = _feed_with_h(thermo)
    with pytest.raises(SplittingError, match="T"):
        split_by_component(feed, {}, thermo, outlet_T={"top": -1.0})
    with pytest.raises(SplittingError, match="P"):
        split_by_component(feed, {}, thermo, outlet_P=0.0)
