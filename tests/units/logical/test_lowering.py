"""Lowering tests: declarative logical nodes onto existing solver features.

adjust lowers to a P2-01 DesignSpec, recycle_block lowers to the P2-03
flowsheet tear options. Each e2e test solves two flowsheets -- one with the
declarative node, one with the explicit solver feature -- and asserts the
solved stream states agree, which is the spec U-A equivalence bar.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.specs import DesignSpec
from ngdesign.solver.design_specs import SequentialModularWithSpecs
from ngdesign.solver.lowering import lower_logical_nodes

FEED = FeedSpec(T=322.15, P=7.0e6, molar_flow=100.0, composition={"C1": 0.848, "nC4": 0.152})


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


def test_adjust_flowsheet_matches_design_spec_solution() -> None:
    thermo = _thermo()
    solver = SequentialModularWithSpecs()
    solved_node = solver.solve(_adjust_flowsheet(with_node=True), thermo)
    solved_explicit = solver.solve(_adjust_flowsheet(with_node=False), thermo)

    a, b = solved_node.streams["S-OUT"], solved_explicit.streams["S-OUT"]
    assert a.T == pytest.approx(320.0, abs=1e-8)
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


def test_recycle_loop_node_and_explicit_forms_agree() -> None:
    thermo = _thermo()
    solver = SequentialModularWithSpecs()
    solved_node = solver.solve(_loop_flowsheet(with_node=True), thermo)
    solved_explicit = solver.solve(_loop_flowsheet(with_node=False), thermo)
    # S-TEAR exists only in the node form; compare the streams both sheets share
    for sid in ("S-MIX", "S-PROD", "S-RCY"):
        a, b = solved_node.streams[sid], solved_explicit.streams[sid]
        assert a.molar_flow == pytest.approx(b.molar_flow, abs=1e-8)
        assert a.T == pytest.approx(b.T, abs=1e-8)
        assert a.enthalpy == pytest.approx(b.enthalpy, abs=1e-8)
