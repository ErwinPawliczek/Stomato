"""Calculation provenance routes (docs/provenance.md section 6).

``GET /api/projects/{id}/trace`` returns the trace graph of a traced solve -
the whole graph, or with ``stream``/``unit`` and ``prop`` the upstream subgraph
of one reported value. ``GET /api/projects/{id}/trace/audit`` lists every output
that rests on uncited data or an unreferenced method.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ngdesign.agent import engine
from ngdesign.api.deps import project_store
from ngdesign.provenance.audit import audit
from ngdesign.provenance.model import AuditReport, TraceGraph
from ngdesign.store import DbProjectStore

router = APIRouter()


def _traced(store: DbProjectStore) -> TraceGraph:
    try:
        _, graph = engine.trace_project(store.get())
    except engine.UnknownPluginError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except engine.InvalidProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return graph


@router.get("/api/projects/{project_id}/trace")
def trace_project(
    store: Annotated[DbProjectStore, Depends(project_store)],
    stream: Annotated[str | None, Query(description="Stream id, e.g. S-002")] = None,
    unit: Annotated[str | None, Query(description="Unit tag, e.g. E-101")] = None,
    prop: Annotated[
        str | None, Query(description="Property: T, P, molar_flow, enthalpy, duty_W, ...")
    ] = None,
) -> TraceGraph:
    """The provenance graph of the solved project, or of one value with stream/unit + prop."""
    graph = _traced(store)
    if stream is None and unit is None:
        return graph
    if prop is None or (stream is not None and unit is not None):
        raise HTTPException(status_code=422, detail="give prop with exactly one of stream or unit")
    node = graph.find(stream=stream, unit=unit, prop=prop)
    if node is None:
        raise HTTPException(status_code=404, detail=f"no traced value {prop!r} for {stream or unit!r}")
    return graph.upstream(node.id)


@router.get("/api/projects/{project_id}/trace/audit")
def trace_audit(store: Annotated[DbProjectStore, Depends(project_store)]) -> AuditReport:
    """Outputs reachable from an uncited leaf or an unreferenced method."""
    return audit(_traced(store))
