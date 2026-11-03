"""Calculation provenance (docs/provenance.md): tracing reproduces the solve exactly,
every leaf is cited, tracing off changes nothing, and the audit sees gaps."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.contracts.flowsheet import FeedSpec, PortRef, StreamSpec, UnitSpec
from ngdesign.provenance import catalogue
from ngdesign.provenance.audit import audit
from ngdesign.provenance.model import Citation, Edge, OpNode, TraceGraph, ValueNode
from ngdesign.provenance.recorder import active, recording

SRC = Path(__file__).resolve().parents[2] / "src" / "ngdesign"

# Light gas: every component's EOS constants and ideal-gas Cp come from cited data sets.
_GAS = {"N2": 0.02, "CO2": 0.03, "C1": 0.80, "C2": 0.09, "C3": 0.06}


def _p(unit: str, port: str) -> PortRef:
    return PortRef(unit=unit, port=port)


def _simple(composition: dict[str, float] = _GAS) -> Flowsheet:
    """Feed -> heater -> separator -> (gas) compressor -> cooler; liquid -> valve."""
    units = [
        UnitSpec(tag="E-101", kind="cooler", params={"T_out": 230.0, "dP": 20e3}),
        UnitSpec(tag="V-101", kind="scrubber", params={"dP": 0.0}),
        UnitSpec(tag="K-101", kind="compressor", params={"P_out": 8.0e6, "eta_isentropic": 0.78}),
        UnitSpec(tag="E-102", kind="cooler", params={"T_out": 310.0, "dP": 15e3}),
        UnitSpec(tag="V-102", kind="jt_valve", params={"P_out": 1.5e6}),
    ]
    streams = [
        StreamSpec(
            id="S-001",
            target=_p("E-101", "inlet"),
            feed=FeedSpec(T=300.0, P=5.0e6, molar_flow=100.0, composition=composition),
        ),
        StreamSpec(id="S-002", source=_p("E-101", "outlet"), target=_p("V-101", "inlet")),
        StreamSpec(id="S-003", source=_p("V-101", "gas_out"), target=_p("K-101", "inlet")),
        StreamSpec(id="S-004", source=_p("V-101", "liquid_out"), target=_p("V-102", "inlet")),
        StreamSpec(id="S-005", source=_p("K-101", "outlet"), target=_p("E-102", "inlet")),
        StreamSpec(id="S-006", source=_p("E-102", "outlet")),
        StreamSpec(id="S-007", source=_p("V-102", "outlet")),
    ]
    return Flowsheet(name="provenance-simple", units=units, streams=streams, thermo="pr")


def _recycle() -> Flowsheet:
    """Feed + make-up -> mixer -> heater -> splitter, 30 % recycled to the mixer."""
    units = [
        UnitSpec(tag="M-101", kind="mixer", params={}),
        # dP = 0 in the loop: a torn pressure with P_out = P_in - dP has Wegstein slope
        # exactly 1 and the bounded-Wegstein factor divides by zero (pre-existing solver issue)
        UnitSpec(tag="E-101", kind="heater", params={"T_out": 320.0, "dP": 0.0}),
        UnitSpec(tag="X-101", kind="splitter", params={"fractions": [0.7, 0.3]}),
    ]
    streams = [
        StreamSpec(
            id="S-001",
            target=_p("M-101", "inlet_1"),
            feed=FeedSpec(T=290.0, P=3.0e6, molar_flow=50.0, composition=_GAS),
        ),
        StreamSpec(
            id="S-006",
            target=_p("M-101", "inlet_3"),
            feed=FeedSpec(T=300.0, P=3.2e6, molar_flow=5.0, composition={"N2": 0.5, "C1": 0.5}),
        ),
        StreamSpec(id="S-002", source=_p("M-101", "outlet"), target=_p("E-101", "inlet")),
        StreamSpec(id="S-003", source=_p("E-101", "outlet"), target=_p("X-101", "inlet")),
        StreamSpec(id="S-004", source=_p("X-101", "outlet_1")),
        StreamSpec(id="S-005", source=_p("X-101", "outlet_2"), target=_p("M-101", "inlet_2")),
    ]
    return Flowsheet(name="provenance-recycle", units=units, streams=streams, thermo="pr")


def _solve(fs: Flowsheet) -> SolvedFlowsheet:
    solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(
        fs, registry.create("thermo", fs.thermo)
    )
    return solved


def _numbers(solved: SolvedFlowsheet) -> str:
    """The solved result minus wall-clock timings (the only nondeterministic field)."""
    data: dict[str, Any] = json.loads(solved.model_dump_json())
    for block in data.get("history", []):
        block.pop("wall_s", None)
    return json.dumps(data, sort_keys=True)


def _traced(fs: Flowsheet) -> tuple[SolvedFlowsheet, TraceGraph]:
    with recording() as rec:
        solved = _solve(fs)
    assert solved.converged and not solved.errors, solved.errors
    return solved, rec.graph()


@pytest.fixture(scope="module")
def simple() -> tuple[SolvedFlowsheet, TraceGraph]:
    return _traced(_simple())


@pytest.fixture(scope="module")
def recycle() -> tuple[SolvedFlowsheet, TraceGraph]:
    return _traced(_recycle())


# ------------------------------------------------------------------ off by default


def test_tracing_is_off_by_default() -> None:
    assert active() is None
    with recording() as rec:
        assert active() is rec
    assert active() is None


@pytest.mark.parametrize("build", [_simple, _recycle])
def test_tracing_changes_no_number(build: Any) -> None:
    fs = build()
    plain = _solve(fs)
    traced, _ = _traced(fs)
    again = _solve(fs)
    assert _numbers(traced) == _numbers(plain) == _numbers(again)


def test_untraced_thermo_calls_record_nothing() -> None:
    thermo = registry.create("thermo", "pr")
    with recording() as rec:
        pass
    thermo.flash_pt(_GAS, 300.0, 5e6, 1.0)  # outside the block: no recorder
    assert rec.graph().values == []


# ------------------------------------------------------------------ outputs reproduce exactly


def _scalar_props(state: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "T": state.T,
        "P": state.P,
        "molar_flow": state.molar_flow,
        "vapor_fraction": state.vapor_fraction,
        "enthalpy": state.enthalpy,
        "entropy": state.entropy,
        "composition": dict(state.composition),
    }
    for phase in state.phases:
        out[f"{phase.kind}.density"] = phase.density
        out[f"{phase.kind}.mole_fraction"] = phase.mole_fraction
    return out


@pytest.mark.parametrize("case", ["simple", "recycle"])
def test_trace_reproduces_every_reported_number(case: str, request: pytest.FixtureRequest) -> None:
    solved, graph = request.getfixturevalue(case)
    for sid, state in solved.streams.items():
        for prop, value in _scalar_props(state).items():
            node = graph.find(stream=sid, prop=prop)
            assert node is not None, f"{sid}.{prop} not traced"
            assert node.value == value, f"{sid}.{prop}: trace {node.value!r} != solve {value!r}"
    for tag, result in solved.units.items():
        for prop in ("duty_W", "power_W"):
            node = graph.find(unit=tag, prop=prop)
            assert node is not None, f"{tag}.{prop} not traced"
            assert node.value == getattr(result, prop)
        for key, value in result.info.items():
            if isinstance(value, float):
                node = graph.find(unit=tag, prop=f"info.{key}")
                assert node is not None and node.value == value, f"{tag}.info.{key}"


# ------------------------------------------------------------------ every leaf cited


@pytest.mark.parametrize("case", ["simple", "recycle"])
def test_every_leaf_has_a_citation(case: str, request: pytest.FixtureRequest) -> None:
    _, graph = request.getfixturevalue(case)
    produced = {e.target for e in graph.edges}
    leaves = [v for v in graph.values if v.id not in produced]
    assert leaves
    uncited = [v.label for v in leaves if v.citation is None]
    assert uncited == []
    assert all(v.quality in ("cited", "user") for v in leaves), [
        (v.label, v.quality) for v in leaves if v.quality not in ("cited", "user")
    ]


@pytest.mark.parametrize("case", ["simple", "recycle"])
def test_audit_is_clean_for_instrumented_units(case: str, request: pytest.FixtureRequest) -> None:
    _, graph = request.getfixturevalue(case)
    report = audit(graph)
    assert report.outputs > 0
    assert report.findings == [], [f.reasons for f in report.findings][:5]


def test_every_operation_is_catalogued_and_referenced(simple: tuple[SolvedFlowsheet, TraceGraph]) -> None:
    _, graph = simple
    for op in graph.ops:
        entry = catalogue.method(op.method)
        assert entry is not None, op.method
        assert op.references or entry.structural, op.method


def test_eos_constants_cite_their_data_set(simple: tuple[SolvedFlowsheet, TraceGraph]) -> None:
    _, graph = simple
    tc = next(v for v in graph.values if v.label == "C1 Tc")
    assert tc.kind == "constant" and tc.quality == "cited"
    assert tc.citation is not None and tc.citation.source == "refprop"
    assert tc.citation.doi == "10.1021/acs.iecr.2c01427"
    kij = next(v for v in graph.values if v.prop == "kij")
    assert kij.citation is not None and kij.citation.source == "chemsep_pr_kij"
    assert kij.citation.reference and "p." in kij.citation.reference


# ------------------------------------------------------------------ structure


def test_flash_consumes_its_specification_not_a_coincident_value(
    simple: tuple[SolvedFlowsheet, TraceGraph],
) -> None:
    """K-101's PH flash takes P from the P_out param and H from the efficiency equation."""
    _, graph = simple
    sub = graph.upstream(graph.find(stream="S-005", prop="T").id)  # type: ignore[union-attr]
    flash = next(o for o in sub.ops if o.method == "flash_ph" and o.unit_tag == "K-101")
    inputs = {e.role: sub.value(e.source) for e in sub.edges if e.target == flash.id}
    assert inputs["P"].prop == "param.P_out" and inputs["P"].kind == "input"
    assert inputs["H"].prop == "h_out"
    assert inputs["z"].stream == "S-003"
    assert flash.iterations is not None
    eff = next(o for o in sub.ops if o.method == "isentropic_compression")
    assert eff.latex and eff.references


def test_recycle_records_converged_tear_with_feedback(recycle: tuple[SolvedFlowsheet, TraceGraph]) -> None:
    solved, graph = recycle
    tears = [o for o in graph.ops if o.method.startswith("tear_")]
    assert len(tears) == 1
    tear = tears[0]
    assert tear.method == "tear_wegstein" and tear.converged
    assert tear.iterations == solved.history[-1].iterations
    assert tear.residual is not None and tear.residual <= 1e-6
    feedback = [e for e in graph.edges if e.feedback]
    assert feedback and all(e.target == tear.id for e in feedback)
    # only the converged pass survives: one flash per unit scope, not one per iteration
    assert sum(1 for o in graph.ops if o.method == "flash_pt" and o.unit_tag == "E-101") == 1


def test_upstream_subgraph_is_closed(simple: tuple[SolvedFlowsheet, TraceGraph]) -> None:
    _, graph = simple
    node = graph.find(unit="K-101", prop="power_W")
    assert node is not None
    sub = graph.upstream(node.id)
    ids = {v.id for v in sub.values} | {o.id for o in sub.ops}
    assert node.id in ids and sub.meta["focus"] == node.id
    assert all(e.source in ids and e.target in ids for e in sub.edges)
    labels = {v.label for v in sub.values}
    assert "K-101 eta_isentropic" in labels and "C1 Tc" in labels


# ------------------------------------------------------------------ audit


def test_audit_flags_outputs_resting_on_uncited_or_unreferenced() -> None:
    graph = TraceGraph(
        values=[
            ValueNode(id="a", label="a", value=1.5, unit="", kind="constant", quality="uncited"),
            ValueNode(
                id="b",
                label="b",
                value=2.5,
                unit="",
                kind="constant",
                quality="estimated",
                citation=Citation(source="joback", citation="group contribution"),
            ),
            ValueNode(id="y", label="y", value=4.0, unit="", kind="output", quality="derived"),
            ValueNode(id="w", label="w", value=2.5, unit="", kind="output", quality="derived"),
        ],
        ops=[
            OpNode(id="f", label="f", method="unrecorded", name="?"),
            OpNode(id="g", label="g", method="identity", name="="),
        ],
        edges=[
            Edge(source="a", target="f"),
            Edge(source="b", target="f"),
            Edge(source="f", target="y"),
            Edge(source="b", target="g"),
            Edge(source="g", target="w"),
        ],
    )
    report = audit(graph)
    by_node = {f.node: f for f in report.findings}
    assert by_node["y"].severity == "error" and set(by_node["y"].culprits) == {"a", "b", "f"}
    assert by_node["w"].severity == "warning" and by_node["w"].culprits == ["b"]
    assert report.clean == 0


def test_estimated_cp_is_flagged_as_warning() -> None:
    """TEG's ideal-gas Cp comes from a Joback estimate: outputs depending on it are warnings."""
    fs = Flowsheet(
        name="provenance-teg",
        units=[UnitSpec(tag="E-101", kind="heater", params={"T_out": 330.0})],
        streams=[
            StreamSpec(
                id="S-001",
                target=_p("E-101", "inlet"),
                feed=FeedSpec(
                    T=300.0, P=5.0e6, molar_flow=10.0, composition={**_GAS, "C3": 0.05, "TEG": 0.01}
                ),
            ),
            StreamSpec(id="S-002", source=_p("E-101", "outlet")),
        ],
        thermo="pr",
    )
    _, graph = _traced(fs)
    report = audit(graph)
    assert report.findings
    assert all(f.severity == "warning" for f in report.findings)
    reasons = {r for f in report.findings for r in f.reasons}
    assert any("TEG Cp_ig" in r for r in reasons)
    assert "unit model default: E-101 dP (default)" in reasons  # dP not given: the unit chose 0


# ------------------------------------------------------------------ catalogue integrity


def test_catalogue_entries_are_referenced_or_structural() -> None:
    for key, entry in catalogue.methods().items():
        if key == "unrecorded":
            assert not entry.references and not entry.structural  # deliberately flagged
            continue
        assert entry.references or entry.structural, key
        for ref in entry.references:
            assert ref.citation.strip(), key


def test_every_method_key_used_in_code_is_catalogued() -> None:
    """Every literal method key passed to rec.equation / rec.derived_state exists."""
    used: set[str] = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            position = {"equation": 3, "derived_state": 1}.get(node.func.attr)
            if position is None or len(node.args) <= position:
                continue
            arg = node.args[position]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                used.add(arg.value)
    assert len(used) > 10, "no instrumented equations found"
    missing = sorted(k for k in used if catalogue.method(k) is None)
    assert missing == []


def test_method_key_sources_resolve() -> None:
    raw = catalogue._method_sources()
    for family in ("constants", "heat_capacity_gas", "vapor_pressure"):
        for key in raw[family]:
            cit, quality = catalogue.method_key_citation(family, key)
            assert cit is not None, (family, key)
            assert quality in ("cited", "estimated")


def test_design_spec_sets_the_manipulated_value() -> None:
    """A design-spec loop's manipulated param is produced by the spec, fed back from its target."""
    base = _simple()
    at_7 = _solve(
        Flowsheet(
            **{
                **base.model_dump(),
                "units": [
                    u.model_copy(update={"params": {**u.params, "P_out": 7.0e6}}) if u.tag == "K-101" else u
                    for u in base.units
                ],
            }
        )
    )
    goal = at_7.units["K-101"].power_W
    spec = {
        "id": "DS-001",
        "target": "K-101.power_W",
        "value": goal,
        "manipulated": "K-101.params.P_out",
        "lower": 6.0e6,
        "upper": 9.0e6,
    }
    fs = Flowsheet(**{**base.model_dump(), "design_specs": [spec]})
    plain = _solve(fs)
    solved, graph = _traced(fs)
    assert _numbers(solved) == _numbers(plain)
    assert solved.design_spec_results[0].converged

    op = next(o for o in graph.ops if o.method == "design_spec_secant")
    assert op.references and op.iterations == solved.design_spec_results[0].iterations
    into = [e for e in graph.edges if e.target == op.id]
    assert {e.role for e in into} == {"target", "achieved"}
    assert next(e for e in into if e.role == "achieved").feedback
    param = next(v for v in graph.values if v.prop == "param.P_out" and v.unit_tag == "K-101")
    assert param.kind == "intermediate" and param.quality == "derived"
    assert param.value == solved.flowsheet.unit("K-101").params["P_out"]
    assert any(e.source == op.id and e.target == param.id for e in graph.edges)
    assert audit(graph).findings == []
