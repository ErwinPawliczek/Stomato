"""Per-flowsheet component slate and opened composition validation (spec P1-02)."""

from __future__ import annotations

import pytest

from ngdesign.contracts import DEFAULT_SLATE, FeedSpec, Flowsheet, PortRef, StreamSpec, StreamState, UnitSpec
from ngdesign.contracts.components import ComponentSet, resolve, resolve_set
from ngdesign.data import components, register_pseudo


@pytest.fixture(scope="module", autouse=True)
def _pseudo() -> None:
    register_pseudo("C7+", "C7+ pseudo", Tb=372.0, sg=0.73)


def _feed(composition: dict[str, float]) -> FeedSpec:
    return FeedSpec(T=300.0, P=1.0e6, molar_flow=100.0, composition=composition)


def test_default_slate_is_the_curated_yaml_keys() -> None:
    assert DEFAULT_SLATE == tuple(components())  # same 18 ids, same order


def test_slate_defaults_to_sorted_feed_components() -> None:
    fs = Flowsheet(
        name="x",
        units=[UnitSpec(tag="MIX-101", kind="mixer")],
        streams=[
            StreamSpec(
                id="F1",
                target=PortRef(unit="MIX-101", port="inlet_1"),
                feed=_feed({"C1": 0.5, "nC5": 0.5}),
            ),
            StreamSpec(id="F2", target=PortRef(unit="MIX-101", port="inlet_2"), feed=_feed({"MeOH": 1.0})),
        ],
    )
    assert fs.components == ["C1", "MeOH", "nC5"]


def test_explicit_slate_round_trips() -> None:
    fs = Flowsheet(
        name="x",
        units=[UnitSpec(tag="MIX-101", kind="mixer")],
        streams=[
            StreamSpec(id="F1", target=PortRef(unit="MIX-101", port="inlet_1"), feed=_feed({"C1": 1.0}))
        ],
        components=["C1", "C2"],  # a component with no feed is legal (intermediate spec)
    )
    assert fs.components == ["C1", "C2"]


def test_feed_component_outside_slate_rejected() -> None:
    with pytest.raises(ValueError, match="not in the flowsheet component slate"):
        Flowsheet(
            name="x",
            units=[UnitSpec(tag="MIX-101", kind="mixer")],
            streams=[
                StreamSpec(id="F1", target=PortRef(unit="MIX-101", port="inlet_1"), feed=_feed({"C1": 1.0}))
            ],
            components=["C2"],
        )


def test_composition_validation_no_longer_checks_membership() -> None:
    """Any non-negative, summing composition constructs: membership moved to the slate."""
    state = StreamState(
        T=300.0,
        P=1.0e6,
        molar_flow=10.0,
        composition={"unobtanium": 1.0},
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )
    assert state.composition == {"unobtanium": 1.0}
    with pytest.raises(ValueError, match="negative mole fraction"):
        StreamState(
            T=300.0,
            P=1.0e6,
            molar_flow=10.0,
            composition={"C1": 1.1, "C2": -0.1},
            vapor_fraction=1.0,
            enthalpy=0.0,
            entropy=0.0,
            phases=[],
        )


def test_resolve_and_resolve_set() -> None:
    heptane = resolve("n-heptane")
    assert heptane.id == "n-heptane"
    assert heptane.kind == "databank"
    slate = resolve_set(["C1", "n-heptane", "C7+"])
    assert isinstance(slate, ComponentSet)
    assert slate.ids == ("C1", "n-heptane", "C7+")


def test_resolve_set_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate component ids"):
        resolve_set(["C1", "C1"])
