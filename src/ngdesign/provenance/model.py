"""The trace graph: value nodes, operation nodes and the edges between them.

A trace is bipartite: values (circles in the UI) are consumed and produced by
operations (boxes). Leaves are values no operation produces; each carries a
citation (a data source or the user's own input). See docs/provenance.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ValueKind = Literal["input", "constant", "parameter", "intermediate", "output"]
Quality = Literal["cited", "user", "estimated", "derived", "uncited"]
TraceValue = float | dict[str, float] | list[list[float]] | str | None


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(_Model):
    """Where a number or a method comes from."""

    source: str
    """Source key, e.g. ``coolprop`` (data/chemdb/sources.yaml) or ``user``."""
    citation: str
    """Full bibliographic text."""
    doi: str | None = None
    url: str | None = None
    table: str | None = None
    """Table or file inside the source, e.g. ``IUPACOrganicCriticalProps.tsv``."""
    reference: str | None = None
    """Row-level reference (paper, page, data-set entry) when the source gives one."""
    grade: str | None = None
    """Source grade (A evaluated, B handbook/measurement, C compilation)."""


class ValueNode(_Model):
    id: str
    label: str
    value: TraceValue
    unit: str
    kind: ValueKind
    quality: Quality
    citation: Citation | None = None
    stream: str | None = None
    unit_tag: str | None = None
    prop: str | None = None
    note: str | None = None


class OpNode(_Model):
    id: str
    label: str
    method: str
    """Method catalogue key (data/provenance/methods.yaml)."""
    name: str
    latex: str | None = None
    references: list[Citation] = []
    """Literature for the method (first = the defining reference). Empty = unreferenced."""
    unit_tag: str | None = None
    calls: int | None = None
    """Thermo calls made inside this operation (iterative units), when counted."""
    iterations: int | None = None
    residual: float | None = None
    converged: bool | None = None
    note: str | None = None


class Edge(_Model):
    source: str
    target: str
    role: str = ""
    feedback: bool = False


class TraceGraph(_Model):
    values: list[ValueNode] = []
    ops: list[OpNode] = []
    edges: list[Edge] = []
    meta: dict[str, str] = {}

    def value(self, node_id: str) -> ValueNode:
        return next(v for v in self.values if v.id == node_id)

    def find(self, *, stream: str | None = None, unit: str | None = None, prop: str) -> ValueNode | None:
        """The output node for a stream property or a unit result (None if absent)."""
        for v in self.values:
            if v.kind != "output" or v.prop != prop:
                continue
            if stream is not None and v.stream == stream:
                return v
            if unit is not None and v.stream is None and v.unit_tag == unit:
                return v
        return None

    def upstream(self, node_id: str) -> TraceGraph:
        """The subgraph of everything ``node_id`` depends on (itself included)."""
        into: dict[str, list[Edge]] = {}
        for e in self.edges:
            into.setdefault(e.target, []).append(e)
        seen = {node_id}
        stack = [node_id]
        edges: list[Edge] = []
        while stack:
            nid = stack.pop()
            for e in into.get(nid, ()):
                edges.append(e)
                if e.source not in seen:
                    seen.add(e.source)
                    stack.append(e.source)
        return TraceGraph(
            values=[v for v in self.values if v.id in seen],
            ops=[o for o in self.ops if o.id in seen],
            edges=edges,
            meta={**self.meta, "focus": node_id},
        )


class AuditFinding(_Model):
    node: str
    """The output value node id."""
    label: str
    severity: Literal["error", "warning"]
    reasons: list[str]
    culprits: list[str]
    """Ids of the uncited/estimated leaves and unreferenced operations it depends on."""


class AuditReport(_Model):
    outputs: int
    clean: int
    findings: list[AuditFinding]
