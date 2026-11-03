"""Public REST API v1 routes (docs/agentic-layer.md section 4).

Every route is a thin HTTP mapping over :class:`ngdesign.agent.service.ProjectService`
(the operations the agent tools and the MCP server run too) or over an existing
``*_core`` of the legacy route modules. Mutations answer ``{result, change}``;
errors answer the v1 envelope (``errors.py``). The caller's ``X-Stomato-Actor``
header (``ui``, a client name, ...) attributes changes; default ``api``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response, StreamingResponse

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.service import (
    OpError,
    ProjectService,
    change_payload,
    component_catalogue,
    thermo_catalogue,
    unit_catalogue,
    unit_kind,
)
from ngdesign.agent.tools import TOOLS, TOOLS_BY_NAME, run_tool
from ngdesign.api import routes_jobs, routes_trace
from ngdesign.api.auth import current_owner
from ngdesign.api.deps import project_store, request_actor
from ngdesign.api.routes_agent import AgentRequest, agent_conversations_core, agent_message_core
from ngdesign.api.routes_export import export_sheet_core
from ngdesign.api.routes_pid import pid_svg_core
from ngdesign.api.routes_projects import ProjectCreate, ProjectInfo, ProjectRename, _info, _source
from ngdesign.api.routes_views import pfd_svg_core
from ngdesign.api.v1.errors import ERROR_RESPONSES
from ngdesign.api.v1.models import (
    ApiIndex,
    CellSet,
    Change,
    ChangeList,
    ComponentsSet,
    DesignSpecIn,
    Mutation,
    StreamCreate,
    StreamPatch,
    ThermoSet,
    ToolInfo,
    ToolRun,
    UnitCreate,
    UnitPatch,
    UnitPosition,
)
from ngdesign.contracts import Project
from ngdesign.jobs.models import Job
from ngdesign.provenance.model import AuditReport, TraceGraph
from ngdesign.store import DbProjectStore, ProjectExists, create_project, list_projects

PREFIX = "/api/v1"
router = APIRouter(prefix=PREFIX, responses=ERROR_RESPONSES)

_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}

#: Seconds between change-log polls in the change stream, and the default
#: lifetime of one stream before the client (EventSource) reconnects.
CHANGE_POLL_SECONDS = 0.5
CHANGE_STREAM_SECONDS = 300.0


def actor(who: Annotated[str, Depends(request_actor)]) -> str:
    """The change attribution for this request (``X-Stomato-Actor``, default ``api``)."""
    return who


Store = Annotated[DbProjectStore, Depends(project_store)]


def service(store: Store, who: Annotated[str, Depends(actor)]) -> ProjectService:
    return ProjectService(store, DEFAULT_ENGINE, actor=who)


Svc = Annotated[ProjectService, Depends(service)]


def _mutation(svc: ProjectService, result: dict[str, Any]) -> Mutation:
    change = Change.model_validate(svc.last_change) if svc.last_change is not None else None
    return Mutation(result=result, change=change)


# --- meta / catalogue ------------------------------------------------------------------------


@router.get("", tags=["meta"])
def index() -> ApiIndex:
    """Entry point: where the schema, docs and tool catalogue live."""
    return ApiIndex(
        version="1",
        openapi="/openapi.json",
        docs="/docs",
        tools=f"{PREFIX}/tools",
        mcp="stomato-mcp (stdio) or stomato-mcp --transport http; see docs/mcp.md",
    )


@router.get("/tools", tags=["meta"])
def tools() -> list[ToolInfo]:
    """The agent tool catalogue — the same names and JSON schemas the in-app agent
    and the MCP server expose (one source of truth)."""
    return [
        ToolInfo(name=t.name, description=t.description, input_schema=t.input_schema, mutates=t.mutates)
        for t in TOOLS
    ]


@router.get("/catalogue/units", tags=["catalogue"])
def catalogue_units(
    registered: Annotated[bool, Query(description="Only kinds with a registered model")] = False,
) -> dict[str, list[dict[str, Any]]]:
    """Every unit kind in palette order (family, then id) with its ports."""
    return {"units": unit_catalogue(registered_only=registered)}


@router.get("/catalogue/units/{kind}", tags=["catalogue"])
def catalogue_unit(kind: str) -> dict[str, Any]:
    """One unit kind: ports, rigour levels with param schemas, references, example params."""
    return unit_kind(kind)


@router.get("/catalogue/components", tags=["catalogue"])
def catalogue_components() -> dict[str, list[dict[str, Any]]]:
    """The curated component slate (id, name, CAS, molar mass g/mol)."""
    return {"components": component_catalogue()}


@router.get("/catalogue/thermo", tags=["catalogue"])
def catalogue_thermo() -> dict[str, list[dict[str, Any]]]:
    """Thermo property packages with status, selectability and registration."""
    return {"thermo": thermo_catalogue()}


# --- projects ---------------------------------------------------------------------------------


@router.get("/projects", tags=["projects"])
def projects(owner: Annotated[str, Depends(current_owner)]) -> dict[str, list[ProjectInfo]]:
    """The caller's projects, oldest first."""
    return {"projects": [_info(row) for row in list_projects(owner)]}


@router.post("/projects", status_code=201, tags=["projects"])
def create(body: ProjectCreate, owner: Annotated[str, Depends(current_owner)]) -> ProjectInfo:
    """Create a project: blank, from a ``template``, a copy (``from_project``) or an explicit body."""
    project, template_id = _source(body, owner)
    try:
        row = create_project(name=body.name, owner=owner, project=project, template=template_id)
    except ProjectExists as exc:
        raise OpError("duplicate_name", str(exc), status=409) from exc
    return _info(row)


@router.get("/projects/{project_id}", tags=["projects"])
def project(store: Store) -> ProjectInfo:
    """One project's identity, version and body."""
    return _info(store.row())


@router.patch("/projects/{project_id}", tags=["projects"])
def rename(body: ProjectRename, store: Store) -> ProjectInfo:
    """Rename a project (logged as an undoable change)."""
    try:
        return _info(store.rename(body.name))
    except ProjectExists as exc:
        raise OpError("duplicate_name", str(exc), status=409) from exc


@router.delete("/projects/{project_id}", tags=["projects"])
def delete(store: Store) -> dict[str, bool]:
    """Delete a project with its conversations and history."""
    store.delete()
    return {"deleted": True}


@router.get("/projects/{project_id}/flowsheet", tags=["projects"])
def flowsheet(svc: Svc) -> dict[str, Any]:
    """The flowsheet: units, streams, thermo, components, design specs."""
    return svc.flowsheet()


# --- thermo and components ----------------------------------------------------------------------


@router.get("/projects/{project_id}/thermo", tags=["thermo"])
def thermo(svc: Svc) -> dict[str, Any]:
    """The selected property package and the component slate."""
    return svc.thermo_state()


@router.put("/projects/{project_id}/thermo", tags=["thermo"])
def set_thermo(body: ThermoSet, svc: Svc) -> Mutation:
    """Select the property package."""
    return _mutation(svc, svc.set_thermo(body.package))


@router.put("/projects/{project_id}/components", tags=["thermo"])
def set_components(body: ComponentsSet, svc: Svc) -> Mutation:
    """Set the component slate (feeds must stay within it)."""
    return _mutation(svc, svc.set_components(body.components))


@router.get("/projects/{project_id}/thermo/recommend", tags=["thermo"])
def recommend(svc: Svc) -> dict[str, Any]:
    """Ranked property-method recommendations for this flowsheet (spec T-08)."""
    return svc.recommend_thermo()


# --- units ------------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/units", tags=["units"])
def units(svc: Svc) -> dict[str, list[dict[str, Any]]]:
    """Every unit with params, placements and connected streams."""
    return {"units": [svc.unit(u.tag) for u in svc.project().flowsheet.units]}


@router.post("/projects/{project_id}/units", status_code=201, tags=["units"])
def add_unit(body: UnitCreate, svc: Svc) -> Mutation:
    """Place a unit from the catalogue, optionally at a position or hex-grid cell."""
    result = svc.place_unit(
        kind=body.kind,
        tag=body.tag,
        params=body.params,
        position=body.position.model_dump() if body.position else None,
        grid=body.grid.model_dump() if body.grid else None,
        view=body.view,
    )
    return _mutation(svc, result)


@router.get("/projects/{project_id}/units/{tag}", tags=["units"])
def unit(tag: str, svc: Svc) -> dict[str, Any]:
    """One unit: kind, params, placements, connected streams."""
    return svc.unit(tag)


@router.patch("/projects/{project_id}/units/{tag}", tags=["units"])
def configure_unit(tag: str, body: UnitPatch, svc: Svc) -> Mutation:
    """Merge (or replace) a unit's params."""
    return _mutation(svc, svc.configure_unit(tag, body.params, replace=body.replace))


@router.put("/projects/{project_id}/units/{tag}/position", tags=["units"])
def move_unit(tag: str, body: UnitPosition, svc: Svc) -> Mutation:
    """Move a unit in the pfd or pid view (position or grid)."""
    result = svc.move_unit(
        tag,
        position=body.position.model_dump() if body.position else None,
        grid=body.grid.model_dump() if body.grid else None,
        view=body.view,
    )
    return _mutation(svc, result)


@router.delete("/projects/{project_id}/units/{tag}", tags=["units"])
def delete_unit(tag: str, svc: Svc) -> Mutation:
    """Delete a unit with its streams and placements."""
    return _mutation(svc, svc.delete_unit(tag))


# --- streams --------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/streams", tags=["streams"])
def streams(svc: Svc) -> dict[str, list[dict[str, Any]]]:
    """Every stream spec (ends, feed, service)."""
    return {"streams": [s.model_dump(mode="json") for s in svc.project().flowsheet.streams]}


@router.post("/projects/{project_id}/streams", status_code=201, tags=["streams"])
def add_stream(body: StreamCreate, svc: Svc) -> Mutation:
    """Add a feed, a connection between two ports, or a product stream."""
    if body.source is None:
        if body.target is None or body.feed is None:
            raise OpError(
                "invalid_project", "a feed stream needs target and feed (or give source to connect)"
            )
        result = svc.add_feed(
            body.target.unit,
            body.target.port,
            body.feed.T,
            body.feed.P,
            body.feed.molar_flow,
            body.feed.composition,
            stream_id=body.id,
            service=body.service,
        )
    else:
        if body.feed is not None:
            raise OpError("invalid_project", "a stream with a source cannot carry a feed")
        result = svc.connect(
            body.source.unit,
            body.source.port,
            body.target.unit if body.target else None,
            body.target.port if body.target else None,
            stream_id=body.id,
            service=body.service,
        )
    return _mutation(svc, result)


@router.get("/projects/{project_id}/streams/{stream_id}", tags=["streams"])
def stream(stream_id: str, svc: Svc) -> dict[str, Any]:
    """One stream spec."""
    return svc.stream(stream_id)


@router.patch("/projects/{project_id}/streams/{stream_id}", tags=["streams"])
def update_stream(stream_id: str, body: StreamPatch, svc: Svc) -> Mutation:
    """Change a stream's service and/or feed fields (null fields unchanged)."""
    feed = body.feed.model_dump() if body.feed is not None else None
    return _mutation(svc, svc.update_stream(stream_id, service=body.service, feed=feed))


@router.delete("/projects/{project_id}/streams/{stream_id}", tags=["streams"])
def delete_stream(stream_id: str, svc: Svc) -> Mutation:
    """Delete one stream."""
    return _mutation(svc, svc.delete_stream(stream_id))


# --- cells and design specs ----------------------------------------------------------------------


@router.get("/projects/{project_id}/cells", tags=["cells"])
def cells(svc: Svc) -> dict[str, Any]:
    """Every writable variable with its value, declared unit and description."""
    return svc.cells()


@router.get("/projects/{project_id}/cells/{address}", tags=["cells"])
def cell(address: str, svc: Svc) -> dict[str, Any]:
    """One writable variable."""
    return svc.cell(address)


@router.put("/projects/{project_id}/cells/{address}", tags=["cells"])
def set_cell(address: str, body: CellSet, svc: Svc) -> Mutation:
    """Set a variable; ``unit`` converts to the declared unit with a dimension check."""
    return _mutation(svc, svc.set_cell(address, body.value, body.unit))


@router.get("/projects/{project_id}/design-specs", tags=["design-specs"])
def design_specs(svc: Svc) -> dict[str, Any]:
    """The flowsheet's design specs."""
    return svc.design_specs()


@router.post("/projects/{project_id}/design-specs", status_code=201, tags=["design-specs"])
def add_design_spec(body: DesignSpecIn, svc: Svc) -> Mutation:
    """Add a design spec (target address driven to value by a manipulated address)."""
    return _mutation(svc, svc.add_design_spec(body.model_dump()))


@router.delete("/projects/{project_id}/design-specs/{spec_id}", tags=["design-specs"])
def delete_design_spec(spec_id: str, svc: Svc) -> Mutation:
    """Remove a design spec."""
    return _mutation(svc, svc.delete_design_spec(spec_id))


# --- solve, jobs and results ----------------------------------------------------------------------


@router.post("/projects/{project_id}/solve", tags=["solve"])
def solve(svc: Svc) -> dict[str, Any]:
    """Solve synchronously (cached by project hash) and return the results summary."""
    return svc.results()


@router.post("/projects/{project_id}/solve/jobs", status_code=202, tags=["solve"])
def solve_job(store: Store) -> routes_jobs.JobEnqueued:
    """Queue a solve on the worker; poll ``GET /api/v1/jobs/{job_id}`` or stream its events."""
    return routes_jobs.enqueue_solve_job(store)


@router.get("/jobs/{job_id}", tags=["solve"])
def job(job_id: str, owner: Annotated[str, Depends(current_owner)]) -> Job:
    """One solve job's status and progress records."""
    return routes_jobs.get_job(job_id, owner)


@router.get("/jobs/{job_id}/events", tags=["solve"])
def job_events(job_id: str, owner: Annotated[str, Depends(current_owner)]) -> StreamingResponse:
    """SSE: one ``progress`` frame per tear record, then ``done`` or ``failed``."""
    return routes_jobs.job_events(job_id, owner)


@router.get("/projects/{project_id}/results", tags=["results"])
def results(svc: Svc) -> dict[str, Any]:
    """Status, diagnostics, design-spec results, per-unit and per-stream summary (SI)."""
    return svc.results()


@router.get("/projects/{project_id}/results/streams/{stream_id}", tags=["results"])
def stream_result(stream_id: str, svc: Svc) -> dict[str, Any]:
    """The full solved state of one stream."""
    return svc.stream_result(stream_id)


@router.get("/projects/{project_id}/results/units/{tag}", tags=["results"])
def unit_result(tag: str, svc: Svc) -> dict[str, Any]:
    """One unit's duty, power, info and outlet states."""
    return svc.unit_result(tag)


@router.get("/projects/{project_id}/results/values/{address}", tags=["results"])
def value(
    address: str,
    svc: Svc,
    unit: Annotated[str | None, Query(description="Convert to this unit, e.g. degC, bar, kW")] = None,
) -> dict[str, Any]:
    """One solved value by address (``S-003.T``, ``K-101.power_W``, ``S-005.x.H2O``)."""
    return svc.read(address, unit)


# --- provenance ------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/trace", tags=["provenance"])
def trace(
    svc: Svc,
    store: Store,
    address: Annotated[str | None, Query(description="Only the upstream graph of this value")] = None,
) -> TraceGraph:
    """The calculation trace of the solved project, or of one value."""
    if address is None:
        return routes_trace._traced(store)
    return TraceGraph.model_validate(svc.explain(address, include_graph=True)["graph"])


@router.get("/projects/{project_id}/trace/explain", tags=["provenance"])
def explain(address: Annotated[str, Query(description="e.g. S-003.T")], svc: Svc) -> dict[str, Any]:
    """How a value was computed: methods with references, inputs with sources, a text summary."""
    return svc.explain(address)


@router.get("/projects/{project_id}/trace/audit", tags=["provenance"])
def audit(store: Store) -> AuditReport:
    """Outputs resting on uncited data or unreferenced methods."""
    return routes_trace.trace_audit(store)


# --- exports ------------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/exports/project.json", tags=["exports"])
def export_project(store: Store) -> Project:
    """The project document (re-importable via POST /api/v1/projects ``project``)."""
    return store.get()


@router.get("/projects/{project_id}/exports/sheet.{fmt}", response_class=Response, tags=["exports"])
def export_sheet(fmt: Literal["csv", "html"], store: Store, scope: str = "all") -> Response:
    """Stream table and datasheets as CSV or HTML."""
    return export_sheet_core(store, fmt, scope)


@router.get(
    "/projects/{project_id}/exports/pfd.svg", response_class=Response, responses=_SVG, tags=["exports"]
)
def export_pfd(store: Store) -> Response:
    """The PFD drawing with the stored placements."""
    return pfd_svg_core(store)


@router.get(
    "/projects/{project_id}/exports/pid.svg", response_class=Response, responses=_SVG, tags=["exports"]
)
def export_pid(store: Store) -> Response:
    """The P&ID drawing (builder + every rule at a fixed point)."""
    return pid_svg_core(store)


# --- history ----------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/changes", tags=["history"])
def changes(
    svc: Svc,
    after: Annotated[int, Query(ge=0, description="Only changes with seq > after")] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ChangeList:
    """The change log, oldest first, each with its actor and structured diff."""
    return ChangeList.model_validate(svc.changes(after=after, limit=limit))


def _change_frames(store: DbProjectStore, after: int, follow: bool, seconds: float) -> Iterator[str]:
    deadline = time.monotonic() + seconds
    last = after
    while True:
        for change in store.changes(after=last, limit=100):
            last = change.seq
            frame = json.dumps({"type": "change", "change": change_payload(change)})
            yield f"id: {change.seq}\ndata: {frame}\n\n"
        if not follow or time.monotonic() >= deadline:
            return
        yield ": keep-alive\n\n"
        time.sleep(CHANGE_POLL_SECONDS)


@router.get("/projects/{project_id}/changes/stream", tags=["history"])
def change_stream(
    store: Store,
    after: Annotated[
        int | None, Query(ge=0, description="Send changes with seq > after; omitted: only new ones")
    ] = None,
    follow: Annotated[bool, Query(description="false: send the backlog and close")] = True,
    seconds: Annotated[float, Query(gt=0, le=3600)] = CHANGE_STREAM_SECONDS,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """SSE: one ``change`` frame per new change from any actor (UI, agent, MCP, API).
    Reads the database, so changes made by another process appear too."""
    if last_event_id is not None and last_event_id.isdigit():
        after = max(after or 0, int(last_event_id))
    if after is None:
        latest = store.changes(after=0, limit=1, newest=True)
        after = latest[0].seq if latest else 0
    return StreamingResponse(
        _change_frames(store, after, follow, seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{project_id}/undo", tags=["history"])
def undo(svc: Svc) -> Mutation:
    """Undo the latest change (409 ``nothing_to_undo`` / ``conflict``)."""
    return _mutation(svc, svc.undo())


@router.post("/projects/{project_id}/redo", tags=["history"])
def redo(svc: Svc) -> Mutation:
    """Redo the latest undone change."""
    return _mutation(svc, svc.redo())


# --- tools and agent ----------------------------------------------------------------------------------


@router.post("/projects/{project_id}/tools/{name}", tags=["tools"])
def run(name: str, body: dict[str, Any], store: Store, who: Annotated[str, Depends(actor)]) -> ToolRun:
    """Run one agent tool by name with its JSON input — the same handler the in-app
    agent and the MCP server call. Tool errors answer the v1 envelope (422)."""
    if name not in TOOLS_BY_NAME:
        raise OpError("unknown_tool", f"unknown tool {name!r}; have {sorted(TOOLS_BY_NAME)}", status=404)
    outcome = run_tool(name, body, store, DEFAULT_ENGINE, actor=who)
    if not outcome.ok:
        raise OpError(outcome.code or "invalid", outcome.error or "tool failed")
    change = Change.model_validate(outcome.change) if outcome.change is not None else None
    return ToolRun(result=outcome.result or {}, change=change)


@router.post("/projects/{project_id}/agent", tags=["agent"])
def agent(req: AgentRequest, store: Store) -> Response:
    """One in-app agent turn as SSE: ``text_delta``, ``tool_call``, ``tool_result``
    (with ``change`` for edits), ``project_changed``, then ``done`` or ``error``."""
    return agent_message_core(store, req)


@router.get("/projects/{project_id}/agent", tags=["agent"])
def agent_conversations(store: Store) -> dict[str, list[str]]:
    """The project's stored conversation ids."""
    return agent_conversations_core(store)
