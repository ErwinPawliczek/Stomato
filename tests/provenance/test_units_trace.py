"""Instrumented unit families (reactors, columns, two-stream exchangers) trace cleanly.

Each unit kind solves its own ``example_case()`` as a one-unit flowsheet (feeds -> unit
-> products), once plain and once under ``recording()``: the traced solve is
bit-identical, every reported stream/unit number has a trace node with the same
value, and the audit finds no error (warnings only for estimated data or model
defaults).
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.contracts.flowsheet import FeedSpec, PortRef, StreamSpec, UnitSpec
from ngdesign.provenance.audit import audit
from ngdesign.provenance.citations import cite_chemdb, cite_species_model
from ngdesign.provenance.model import TraceGraph
from ngdesign.provenance.recorder import recording

#: (catalogue row, level) pairs whose unit records its own equations.
REACTORS = [
    "conversion_reactor/R0",
    "yield_reactor/R0",
]
COLUMNS: list[str] = []
EXCHANGERS: list[str] = []
INSTRUMENTED = REACTORS + COLUMNS + EXCHANGERS

_TAG = "U-101"


def _flowsheet(row: str, level: str) -> Flowsheet:
    """Feeds -> the unit -> one product stream per outlet port (as test_unit_balances)."""
    unit = registry.create("unit", row)
    feeds, params = type(unit)._adapters[level].example_case()
    streams = [
        StreamSpec(
            id=f"F-1{i:02d}",
            target=PortRef(unit=_TAG, port=port),
            feed=f if isinstance(f, FeedSpec) else FeedSpec(**f),
        )
        for i, (port, f) in enumerate(feeds.items())
    ]
    streams += [
        StreamSpec(id=f"P-2{i:02d}", source=PortRef(unit=_TAG, port=port))
        for i, port in enumerate(unit.outlet_ports)
    ]
    return Flowsheet(
        name=f"trace-{row}-{level}",
        units=[UnitSpec(tag=_TAG, kind=row, params={**params, "model": level})],
        streams=streams,
        thermo="pr",
    )


def _solve(fs: Flowsheet) -> SolvedFlowsheet:
    solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(
        fs, registry.create("thermo", fs.thermo)
    )
    return solved


def _numbers(solved: SolvedFlowsheet) -> str:
    data: dict[str, Any] = json.loads(solved.model_dump_json())
    for block in data.get("history", []):
        block.pop("wall_s", None)
    return json.dumps(data, sort_keys=True)


def _stream_props(state: Any) -> dict[str, Any]:
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


def _flat(info: dict[str, Any], prefix: str = "") -> list[tuple[str, float]]:
    """Numeric ``info`` entries under the names the recorder binds them by."""
    out: list[tuple[str, float]] = []
    for key, value in info.items():
        path = f"{prefix}{key}"
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            out.append((path, float(value)))
        elif (
            isinstance(value, list | tuple)
            and value
            and all(isinstance(x, int | float) and not isinstance(x, bool) for x in value)
        ):
            out.extend((f"{path}[{i}]", float(x)) for i, x in enumerate(value))
        elif isinstance(value, list | tuple) and value and all(isinstance(x, dict) for x in value):
            for i, x in enumerate(value):
                out.extend(_flat(x, f"{path}[{i}]."))
        elif isinstance(value, dict):
            if (
                value
                and all(isinstance(x, int | float) for x in value.values())
                and math.isclose(sum(value.values()), 1.0, abs_tol=1e-6)
                and len(value) > 1
            ):
                continue  # composition-like mappings are not bound as numbers
            out.extend(_flat(value, f"{path}."))
    return out


def _same(a: Any, b: Any) -> bool:
    return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))


def _check(solved: SolvedFlowsheet, graph: TraceGraph) -> None:
    for sid, state in solved.streams.items():
        for prop, value in _stream_props(state).items():
            node = graph.find(stream=sid, prop=prop)
            assert node is not None, f"{sid}.{prop} not traced"
            assert _same(node.value, value), f"{sid}.{prop}: trace {node.value!r} != solve {value!r}"
    for tag, result in solved.units.items():
        for prop in ("duty_W", "power_W"):
            node = graph.find(unit=tag, prop=prop)
            assert node is not None, f"{tag}.{prop} not traced"
            assert node.value == getattr(result, prop), f"{tag}.{prop}"
        for key, value in _flat(result.info):
            node = graph.find(unit=tag, prop=f"info.{key}")
            assert node is not None, f"{tag}.info.{key} not traced"
            assert _same(node.value, value), f"{tag}.info.{key}: trace {node.value!r} != solve {value!r}"


@pytest.mark.parametrize("name", INSTRUMENTED)
def test_unit_traces_cleanly(name: str) -> None:
    row, level = name.split("/")
    fs = _flowsheet(row, level)
    plain = _solve(fs)
    with recording(flowsheet=fs.name) as rec:
        traced = _solve(fs)
    assert traced.converged and not traced.errors, traced.errors
    assert _numbers(traced) == _numbers(plain), "tracing changed a number"
    graph = rec.graph()
    _check(traced, graph)
    report = audit(graph)
    errors = [(f.label, f.reasons) for f in report.findings if f.severity == "error"]
    assert errors == [], errors[:3]
    assert not any(o.method.startswith("unit_model:") for o in graph.ops), "unit fell back to the generic op"


# ------------------------------------------------------------------ helpers


def test_cited_leaf_carries_its_citation_and_is_shared() -> None:
    cit = cite_chemdb("CH4", "Hf_gas")
    assert cit is not None and cit.source == "atct" and cit.reference
    with recording() as rec:
        a = rec.cited("CH4 ΔfH°298", -74534.0, "J/mol", cit)
        b = rec.cited("CH4 ΔfH°298", -74534.0, "J/mol", cit)
        c = rec.cited("XX ΔfH°298", 1.5, "J/mol", None)
    assert a.id == b.id
    nodes = {v.id: v for v in rec.graph().values}
    assert nodes[a.id].quality == "cited" and nodes[a.id].kind == "constant"
    assert nodes[a.id].citation == cit
    assert nodes[c.id].quality == "uncited"


def test_species_model_citation_names_the_janaf_table() -> None:
    from ngdesign.data.formation import gas_model

    cit = cite_species_model(gas_model("CH4"))
    assert cit is not None and cit.source == "janaf" and cit.table == gas_model("CH4").model.split(":")[1]


def test_results_records_one_operation_with_flattened_outputs() -> None:
    with recording() as rec, rec.scope("u", unit_tag="X-1"):
        refs = rec.results(
            "column_shortcut", {"Nmin": 5.5, "profile": {"T_K": [300.5, 310.5]}}, {"a": 2.5}, iterations=7
        )
    graph = rec.graph()
    assert set(refs) == {"Nmin", "profile.T_K[0]", "profile.T_K[1]"}
    (op,) = [o for o in graph.ops if o.method == "column_shortcut"]
    assert op.iterations == 7
    produced = {e.target for e in graph.edges if e.source == op.id}
    assert {r.id for r in refs.values()} <= produced
    assert graph.value(refs["profile.T_K[1]"].id).unit == "K"
