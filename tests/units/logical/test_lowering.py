"""Lowering tests: declarative logical nodes onto existing solver features.

adjust lowers to a P2-01 DesignSpec, recycle_block lowers to the P2-03
flowsheet tear options. Each e2e test solves two flowsheets -- one with the
declarative node, one with the explicit solver feature -- and asserts the
solved stream states agree, which is the spec U-A equivalence bar.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.specs import DesignSpec
from ngdesign.flowsheets.slice import build as build_slice
from ngdesign.solver.design_specs import SequentialModularWithSpecs
from ngdesign.solver.lowering import lower_logical_nodes
from tests.solver.test_sequential_modular import FAKES, _port
from tests.solver.test_sequential_modular import _feed as _p2_feed

if TYPE_CHECKING:
    from collections.abc import Iterator

FEED = FeedSpec(T=322.15, P=7.0e6, molar_flow=100.0, composition={"C1": 0.848, "nC4": 0.152})


@contextmanager
def _fake_units_registered() -> Iterator[None]:
    """Register the P2-03 fake units for the loop solve and remove them after.

    Same registration dance as the P2-03 test module's autouse fixture (the
    fake kinds live only there); kept out of the registry the rest of the run.
    """
    for name, cls in FAKES.items():
        registry.register("unit", name)(cls)
    try:
        yield
    finally:
        for name in FAKES:
            registry._REGISTRY["unit"].pop(name, None)


def _thermo() -> Thermo:
    names = registry.available("thermo")
    thermo: Thermo = registry.create("thermo", "pr" if "pr" in names else names[0])
    return thermo


def _stream(sid: str, source: PortRef | None, target: PortRef | None = None) -> StreamSpec:
    return StreamSpec(id=sid, source=source, target=target)


# --------------------------------------------------------------- adjust


def _adjust_flowsheet(with_node: bool) -> Flowsheet:
    """Heater to 320 K, declared either as an adjust node or as a DesignSpec."""
    streams = [
        StreamSpec(id="S-FEED", source=None, target=PortRef(unit="H-100", port="inlet"), feed=FEED),
    ]
    if with_node:
        # the adjust node sits in the chain (identity), so the sheet has no
        # unwired ports for the solver to read as a unit error
        streams += [
            _stream("S-MID", PortRef(unit="H-100", port="outlet"), PortRef(unit="ADJ-101", port="inlet")),
            _stream("S-OUT", PortRef(unit="ADJ-101", port="outlet")),
        ]
    else:
        streams.append(_stream("S-OUT", PortRef(unit="H-100", port="outlet")))
    if with_node:
        units = [
            UnitSpec(tag="H-100", kind="heater", params={"T_out": 300.0}),
            UnitSpec(
                tag="ADJ-101",
                kind="adjust",
                params={
                    "target": {"stream": "S-OUT", "variable": "T", "value": 320.0},
                    "manipulate": {"unit": "H-100", "param": "T_out"},
                    "bounds": {"lower": 250.0, "upper": 450.0},
                },
            ),
        ]
        return Flowsheet(name="F-ADJ", units=units, streams=streams)
    units = [UnitSpec(tag="H-100", kind="heater", params={"T_out": 300.0})]
    specs = [
        DesignSpec(
            id="DS-1",
            target="S-OUT.T",
            value=320.0,
            manipulated="H-100.params.T_out",
            lower=250.0,
            upper=450.0,
        )
    ]
    return Flowsheet(name="F-ADJ", units=units, streams=streams, design_specs=specs)


def test_lowering_is_identity_without_logical_nodes() -> None:
    fs = _adjust_flowsheet(with_node=False).model_copy(update={"design_specs": []})
    assert lower_logical_nodes(fs) is fs


def test_adjust_lowers_to_the_equivalent_design_spec() -> None:
    fs = _adjust_flowsheet(with_node=True)
    lowered = lower_logical_nodes(fs)
    assert [s.id for s in lowered.design_specs] == ["DS-ADJ-101"]
    spec = lowered.design_specs[0]
    assert spec.target == "S-OUT.T" and spec.value == 320.0
    assert spec.manipulated == "H-100.params.T_out"
    assert (spec.lower, spec.upper) == (250.0, 450.0)
    # the node stays an identity unit in the graph
    assert any(u.tag == "ADJ-101" for u in lowered.units)


def test_adjust_lowering_is_idempotent() -> None:
    lowered = lower_logical_nodes(_adjust_flowsheet(with_node=True))
    twice = lower_logical_nodes(lowered)
    assert [s.id for s in twice.design_specs] == ["DS-ADJ-101"]
    assert twice.solver_options == lowered.solver_options


def test_adjust_refuses_an_incomplete_declaration() -> None:
    fs = _adjust_flowsheet(with_node=True)
    broken = fs.model_copy(
        update={
            "units": [
                UnitSpec(tag="H-100", kind="heater", params={"T_out": 300.0}),
                UnitSpec(
                    tag="ADJ-101",
                    kind="adjust",
                    # complete target, no manipulate: the manipulate refusal is what fires
                    params={"target": {"stream": "S-OUT", "variable": "T", "value": 320.0}},
                ),
            ]
        }
    )
    with pytest.raises(ValueError, match="manipulate"):
        lower_logical_nodes(broken)


def _slice_with_design_spec() -> Flowsheet:
    """The P2-01 sheet (tests/solver/test_design_specs.py): the locked slice with
    S-003.T set to 390 K via K-101.params.P_out."""
    fs = build_slice()
    spec = DesignSpec(
        id="DS-001",
        target="S-003.T",
        value=390.0,
        manipulated="K-101.params.P_out",
        lower=6e6,
        upper=14e6,
    )
    return fs.model_copy(update={"design_specs": [spec]})


def _slice_with_adjust_node() -> Flowsheet:
    """The same sheet, the spec declared as an adjust node in S-003's path."""
    fs = build_slice()
    units = list(fs.units) + [
        UnitSpec(
            tag="ADJ-101",
            kind="adjust",
            params={
                "target": {"stream": "S-003", "variable": "T", "value": 390.0},
                "manipulate": {"unit": "K-101", "param": "P_out"},
                "bounds": {"lower": 6e6, "upper": 14e6},
            },
        )
    ]
    streams: list[StreamSpec] = []
    for stream in fs.streams:
        if stream.id == "S-003":
            streams.append(stream.model_copy(update={"source": PortRef(unit="ADJ-101", port="outlet")}))
            streams.append(
                StreamSpec(
                    id="S-KADJ",
                    source=PortRef(unit="K-101", port="outlet"),
                    target=PortRef(unit="ADJ-101", port="inlet"),
                    service=stream.service,
                )
            )
        else:
            streams.append(stream)
    return fs.model_copy(update={"units": units, "streams": streams, "design_specs": []})


def test_adjust_on_the_p2_01_slice_sheet_matches_the_design_spec() -> None:
    """E2E equivalence on the flowsheet the P2-01 tests already solve."""
    thermo = _thermo()
    solver = SequentialModularWithSpecs()
    solved_node = solver.solve(_slice_with_adjust_node(), thermo)
    solved_explicit = solver.solve(_slice_with_design_spec(), thermo)

    a, b = solved_node.streams["S-003"], solved_explicit.streams["S-003"]
    assert a.T == pytest.approx(390.0, rel=1e-4)
    assert a.T == pytest.approx(b.T, abs=1e-8)
    assert a.molar_flow == pytest.approx(b.molar_flow, abs=1e-8)
    assert a.enthalpy == pytest.approx(b.enthalpy, abs=1e-8)


# --------------------------------------------------------- recycle_block


def _loop_flowsheet(with_node: bool) -> Flowsheet:
    """Feed + trim mixed, 50/50 split, the second half recycled."""
    units: list[UnitSpec] = [
        UnitSpec(tag="M-101", kind="mixer", params={}),
        UnitSpec(tag="X-201", kind="component_splitter", params={"fractions": {"C1": 0.5, "nC4": 0.5}}),
    ]
    if with_node:
        units.append(UnitSpec(tag="RCY-301", kind="recycle_block", params={"acceleration": "wegstein"}))
    tear_target = (
        PortRef(unit="RCY-301", port="inlet") if with_node else PortRef(unit="M-101", port="inlet_2")
    )
    streams = [
        StreamSpec(id="S-FEED", source=None, target=PortRef(unit="M-101", port="inlet_1"), feed=FEED),
        StreamSpec(
            id="S-TRIM",
            source=None,
            target=PortRef(unit="M-101", port="inlet_3"),
            feed=FeedSpec(T=322.15, P=7.0e6, molar_flow=10.0, composition={"C1": 1.0}),
        ),
        _stream("S-MIX", PortRef(unit="M-101", port="outlet"), PortRef(unit="X-201", port="inlet")),
        _stream("S-PROD", PortRef(unit="X-201", port="outlet_1")),
        _stream("S-RCY", PortRef(unit="X-201", port="outlet_2"), tear_target),
    ]
    if with_node:
        streams.append(
            _stream("S-TEAR", PortRef(unit="RCY-301", port="outlet"), PortRef(unit="M-101", port="inlet_2"))
        )
    return Flowsheet(name="F-LOOP", units=units, streams=streams)


def test_recycle_block_lowers_to_tear_options() -> None:
    def _flowsheet(params: dict[str, Any]) -> Flowsheet:
        return Flowsheet(
            name="F-RCY",
            units=[
                UnitSpec(tag="M-101", kind="mixer", params={}),
                UnitSpec(tag="RCY-301", kind="recycle_block", params=params),
            ],
            streams=[
                StreamSpec(id="S-1", source=None, target=PortRef(unit="M-101", port="inlet_1"), feed=FEED)
            ],
        )

    lowered = lower_logical_nodes(_flowsheet({"acceleration": "wegstein", "tolerance": 1e-10}))
    assert lowered.solver_options.tear_acceleration == "wegstein"
    assert lowered.solver_options.rtol == pytest.approx(1e-10)
    none_lowered = lower_logical_nodes(_flowsheet({"acceleration": "none"}))
    assert none_lowered.solver_options.tear_acceleration == "direct"


def test_conflicting_recycle_blocks_are_refused() -> None:
    fs = Flowsheet(
        name="F-CONFLICT",
        units=[
            UnitSpec(tag="M-101", kind="mixer", params={}),
            UnitSpec(tag="RCY-301", kind="recycle_block", params={"acceleration": "wegstein"}),
            UnitSpec(tag="RCY-302", kind="recycle_block", params={"acceleration": "broyden"}),
        ],
        streams=[StreamSpec(id="S-1", source=None, target=PortRef(unit="M-101", port="inlet_1"), feed=FEED)],
    )
    with pytest.raises(ValueError, match="conflicts with"):
        lower_logical_nodes(fs)


def test_recycle_loop_solves_to_the_hand_computed_split() -> None:
    thermo = _thermo()
    solver = SequentialModularWithSpecs()
    solved = solver.solve(_loop_flowsheet(with_node=True), thermo)
    assert solved.converged
    mix = solved.streams["S-MIX"]
    # m = (F + trim) + m/2  =>  m = 2 x 110 = 220 mol/s
    assert mix.molar_flow == pytest.approx(220.0, abs=1e-6)
    assert solved.streams["S-PROD"].molar_flow == pytest.approx(110.0, abs=1e-6)
    assert solved.streams["S-TEAR"].molar_flow == pytest.approx(110.0, abs=1e-6)


def _p2_loop_flowsheet(with_node: bool) -> Flowsheet:
    """The P2-03 loop (tests/solver/test_sequential_modular.py::
    test_recycle_loop_converges): 100 mol/s fresh feed, 40% of the mixed
    stream recycled through a 5 K heater, fake units registered by that test
    module's ``_fake_units`` context."""
    units: list[UnitSpec] = [
        UnitSpec(tag="MIX-101", kind="fake_mixer"),
        UnitSpec(tag="HTR-101", kind="fake_heater", params={"dT": 5.0}),
        UnitSpec(tag="SPL-101", kind="fake_splitter", params={"f": 0.4}),
    ]
    if with_node:
        units.append(UnitSpec(tag="RCY-301", kind="recycle_block", params={"acceleration": "wegstein"}))
    in_b = PortRef(unit="RCY-301", port="inlet") if with_node else _port("MIX-101", "in_b")
    streams = [
        StreamSpec(id="S-001", target=_port("MIX-101", "in_a"), feed=_p2_feed(100.0)),
        StreamSpec(id="S-002", source=_port("SPL-101", "out_a"), target=in_b),
        StreamSpec(id="S-003", source=_port("MIX-101", "out"), target=_port("HTR-101", "inlet")),
        StreamSpec(id="S-004", source=_port("HTR-101", "outlet"), target=_port("SPL-101", "inlet")),
        StreamSpec(id="S-005", source=_port("SPL-101", "out_b")),
    ]
    if with_node:
        streams.append(
            StreamSpec(
                id="S-TEAR",
                source=PortRef(unit="RCY-301", port="outlet"),
                target=_port("MIX-101", "in_b"),
            )
        )
    return Flowsheet(name="F-P2-LOOP", units=units, streams=streams)


def test_recycle_block_on_the_p2_03_loop_matches_the_explicit_form() -> None:
    """E2E equivalence on the flowsheet the P2-03 tests already solve."""
    thermo = _thermo()
    solver = SequentialModularWithSpecs()
    with _fake_units_registered():
        solved_node = solver.solve(_p2_loop_flowsheet(with_node=True), thermo)
        solved_explicit = solver.solve(_p2_loop_flowsheet(with_node=False), thermo)
        for sid in ("S-002", "S-003", "S-005"):
            a, b = solved_node.streams[sid], solved_explicit.streams[sid]
            assert a.molar_flow == pytest.approx(b.molar_flow, abs=1e-8)
            assert a.T == pytest.approx(b.T, abs=1e-8)
            assert a.enthalpy == pytest.approx(b.enthalpy, abs=1e-8)
