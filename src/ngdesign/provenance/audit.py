"""Audit a trace: which outputs depend on uncited data or unreferenced methods.

An output is flagged **error** when its upstream reaches a leaf with quality
``uncited`` or an operation that is neither referenced nor structural (an
uninstrumented unit model, an unrecorded calculation, an unknown method key),
and **warning** when the worst it reaches is an ``estimated`` leaf or a
``model_default`` input (a value the unit chose because the user gave none).
"""

from __future__ import annotations

from ngdesign.provenance import catalogue
from ngdesign.provenance.model import AuditFinding, AuditReport, OpNode, TraceGraph, ValueNode


def op_is_cited(op: OpNode) -> bool:
    """True for operations with literature or a structural (bookkeeping) catalogue entry."""
    if op.references:
        return True
    entry = catalogue.method(op.method)
    return entry is not None and entry.structural


def leaf_problem(v: ValueNode) -> tuple[str, str] | None:
    """(severity, reason) for a leaf that is not cleanly cited, else None."""
    if v.quality == "uncited" or (v.citation is None and v.quality not in ("derived",)):
        return "error", f"uncited value: {v.label}"
    if v.quality == "estimated":
        return "warning", f"estimated value: {v.label}"
    if v.citation is not None and v.citation.source == "model_default":
        return "warning", f"unit model default: {v.label}"
    return None


def audit(graph: TraceGraph) -> AuditReport:
    """Walk upstream from every output value and collect what it rests on."""
    values = {v.id: v for v in graph.values}
    ops = {o.id: o for o in graph.ops}
    into: dict[str, list[str]] = {}
    for e in graph.edges:
        into.setdefault(e.target, []).append(e.source)
    problems: dict[str, tuple[str, str]] = {}
    for vid, v in values.items():
        if vid not in into:  # a leaf
            p = leaf_problem(v)
            if p is not None:
                problems[vid] = p
        elif v.quality == "uncited":  # produced by an unrecorded calculation
            problems[vid] = ("error", f"unattributed value: {v.label}")
    for oid, o in ops.items():
        if not op_is_cited(o):
            problems[oid] = ("error", f"no method reference: {o.label} [{o.method}]")

    findings: list[AuditFinding] = []
    outputs = [v for v in graph.values if v.kind == "output"]
    memo: dict[str, frozenset[str]] = {}

    def culprits(start: str) -> frozenset[str]:
        # iterative DFS with memo over the (feedback-free) upstream graph
        if start in memo:
            return memo[start]
        seen: set[str] = set()
        stack = [start]
        found: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            if nid in memo:
                found |= memo[nid]
                continue
            if nid in problems:
                found.add(nid)
            stack.extend(into.get(nid, ()))
        result = frozenset(found)
        memo[start] = result
        return result

    for v in outputs:
        bad = culprits(v.id)
        if not bad:
            continue
        severity = "error" if any(problems[c][0] == "error" for c in bad) else "warning"
        findings.append(
            AuditFinding(
                node=v.id,
                label=v.label,
                severity=severity,
                reasons=sorted({problems[c][1] for c in bad}),
                culprits=sorted(bad),
            )
        )
    return AuditReport(outputs=len(outputs), clean=len(outputs) - len(findings), findings=findings)
