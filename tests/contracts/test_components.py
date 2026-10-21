"""Per-flowsheet component slate and opened composition validation (spec P1-02)."""

from __future__ import annotations

import pytest

from ngdesign.contracts import DEFAULT_SLATE, FeedSpec, Flowsheet, PortRef, StreamSpec, StreamState, UnitSpec
from ngdesign.contracts.components import (
    ComponentRef,
    ComponentSet,
    PseudoDefinition,
    resolve,
    resolve_set,
)
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


# ------------------------------------------------------------------ spec P1-07


def test_pseudo_definition_resolves_through_the_slate() -> None:
    refs: list[ComponentRef] = [
        "C1",
        PseudoDefinition(id="C7+", name="C7+ pseudo", Tb=372.0, sg=0.73),
    ]
    slate = resolve_set(refs)
    assert slate.ids == ("C1", "C7+")
    assert slate.components[1].kind == "pseudo"
    assert slate.components[1].Tb == 372.0
    assert [d.id for d in slate.pseudo_definitions] == ["C7+"]
    assert slate.pseudo_definitions[0].Tb == 372.0


def test_string_entries_still_use_the_registered_default() -> None:
    slate = resolve_set(["C1", "C7+"])  # C7+ registered by the module fixture
    assert slate.components[1].kind == "pseudo"
    assert slate.components[1].Tb == 372.0


def test_flowsheet_owned_definitions_and_registered_defaults_are_distinct_sources() -> None:
    slate = resolve_set(["C7+", PseudoDefinition(id="C9+", name="C9+ pseudo", Tb=450.0, sg=0.82)])
    assert slate.components[0].Tb == 372.0  # string entry: the registered default
    assert slate.components[1].Tb == 450.0  # definition entry: the flowsheet's own


def test_mixing_both_forms_for_the_same_id_is_a_duplicate() -> None:
    with pytest.raises(ValueError, match="duplicate component ids"):
        resolve_set(["C7+", PseudoDefinition(id="C7+", name="C7+ pseudo", Tb=430.0, sg=0.80)])


def test_override_needs_a_provenance_note() -> None:
    with pytest.raises(ValueError, match="provenance"):
        PseudoDefinition(id="C7+", name="C7+ pseudo", Tb=372.0, sg=0.73, Tc=600.0)


def test_override_applies_with_its_note() -> None:
    definition = PseudoDefinition(
        id="C7+", name="C7+ pseudo", Tb=372.0, sg=0.73, Tc=600.0, provenance={"Tc": "lab PVT cell"}
    )
    record = resolve_set([definition]).components[0]
    assert record.Tc == 600.0
    assert record.provenance["Tc"] == "lab PVT cell"
    assert "Kesler" in record.provenance["Pc"]  # the rest stays correlation-graded


def test_pseudo_definition_needs_positive_tb_and_sg() -> None:
    with pytest.raises(ValueError, match="positive Tb and sg"):
        PseudoDefinition(id="C7+", name="C7+ pseudo", Tb=-1.0, sg=0.73)


def test_flowsheet_pseudo_round_trips_through_project_json() -> None:
    fs = Flowsheet(
        name="owned-pseudo",
        units=[UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [0.5, 0.5]})],
        streams=[
            StreamSpec(
                id="F1",
                target=PortRef(unit="SPL-101", port="inlet"),
                feed=FeedSpec(T=300.0, P=20.0e5, molar_flow=100.0, composition={"C1": 0.5, "C7+": 0.5}),
            ),
            StreamSpec(id="P1", source=PortRef(unit="SPL-101", port="outlet_1")),
        ],
        components=["C1", PseudoDefinition(id="C7+", name="C7+ pseudo", Tb=372.0, sg=0.73)],
    )
    assert fs.slate_ids() == ["C1", "C7+"]
    revived = Flowsheet.model_validate_json(fs.model_dump_json())
    assert revived == fs
    assert isinstance(revived.components[1], PseudoDefinition)
    assert revived.components[1].Tb == 372.0


def test_flowsheet_rejects_pseudo_shadowing_a_curated_id() -> None:
    with pytest.raises(ValueError, match="reserved by the curated slate"):
        Flowsheet(
            name="x",
            units=[UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [0.5, 0.5]})],
            streams=[
                StreamSpec(
                    id="F1",
                    target=PortRef(unit="SPL-101", port="inlet"),
                    feed=FeedSpec(T=300.0, P=20.0e5, molar_flow=100.0, composition={"C1": 1.0}),
                ),
                StreamSpec(id="P1", source=PortRef(unit="SPL-101", port="outlet_1")),
            ],
            components=["C1", PseudoDefinition(id="C1", name="methane pseudo", Tb=111.7, sg=0.3)],
        )


def test_flowsheet_schema_carries_the_union() -> None:
    rendered = str(Flowsheet.model_json_schema()["properties"]["components"])
    assert "PseudoDefinition" in rendered
