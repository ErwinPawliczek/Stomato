"""Project-scoped API (spec P3-01): every /api route addressed by project id.

One twin per legacy unscoped route — the legacy handler stays the deprecated
alias bound to the ``default`` project, and each ``*_core`` in the route modules
is the single implementation both call. The store dependency (deps.py) does the
owner check: a foreign project is 403 before any handler runs.

PUT /api/projects/{id} carries ``expected_version`` as a query parameter (the
body is the locked ``Project`` contract, so the version rides outside it): a
stale version answers 409 via the ProjectConflict handler in app.py. GET
/api/projects/{id} returns ``version`` for clients to round-trip.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ngdesign.api.auth import current_owner
from ngdesign.api.deps import project_store
from ngdesign.api.routes_agent import (
    AgentRequest,
    agent_conversation_delete_core,
    agent_conversations_core,
    agent_message_core,
    agent_transcript_core,
)
from ngdesign.api.routes_export import export_sheet_core
from ngdesign.api.routes_iso import iso_lines_core, iso_sheet_core, iso_svg_core, place_iso_core
from ngdesign.api.routes_pid import pid_svg_core
from ngdesign.api.routes_plot import plot_svg_core, route_core
from ngdesign.api.routes_solve import solve_core
from ngdesign.api.routes_views import pfd_svg_core
from ngdesign.contracts import XY, IsoSheet, Layout, PipingNetwork, Project, SolvedFlowsheet, Vec3
from ngdesign.store import DbProjectStore, ProjectExists, ProjectRow, create_project, list_projects

router = APIRouter()

_SVG_RESPONSES: dict[int | str, dict[str, object]] = {200: {"content": {"image/svg+xml": {}}}}


class ProjectInfo(BaseModel):
    """A stored project: identity, audit stamp, version, and the body."""

    id: str
    name: str
    owner: str
    version: int
    created_at: datetime
    updated_at: datetime
    project: Project


def _info(row: ProjectRow) -> ProjectInfo:
    return ProjectInfo(
        id=row.id,
        name=row.name,
        owner=row.owner,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        project=Project.model_validate_json(row.body_json),
    )


class ProjectCreate(BaseModel):
    """POST /api/projects body."""

    name: str = Field(min_length=1)
    project: Project


@router.get("/api/projects")
def projects(owner: Annotated[str, Depends(current_owner)]) -> dict[str, list[ProjectInfo]]:
    """The caller's projects (the token's owner; open mode: 'local')."""
    return {"projects": [_info(row) for row in list_projects(owner)]}


@router.post("/api/projects", status_code=201)
def create_project_route(body: ProjectCreate, owner: Annotated[str, Depends(current_owner)]) -> ProjectInfo:
    """Create a project; 409 when the owner already has one with this name."""
    try:
        row = create_project(name=body.name, owner=owner, project=body.project)
    except ProjectExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _info(row)


@router.get("/api/projects/{project_id}")
def get_project_route(store: Annotated[DbProjectStore, Depends(project_store)]) -> ProjectInfo:
    """One project's identity, version and body."""
    return _info(store.row())


@router.put("/api/projects/{project_id}")
def put_project_route(
    project: Project,
    store: Annotated[DbProjectStore, Depends(project_store)],
    expected_version: int | None = None,
) -> ProjectInfo:
    """Replace a project's body; 409 when expected_version is stale."""
    from ngdesign.store import ProjectConflict

    try:
        store.put(project, expected_version=expected_version)
    except ProjectConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _info(store.row())


@router.delete("/api/projects/{project_id}")
def delete_project_route(store: Annotated[DbProjectStore, Depends(project_store)]) -> dict[str, bool]:
    """Delete a project and its conversations."""
    store.delete()
    return {"deleted": True}


@router.post("/api/projects/{project_id}/solve")
def solve_project_route(store: Annotated[DbProjectStore, Depends(project_store)]) -> SolvedFlowsheet:
    """Solve a project; 501 naming the kind when a unit is missing."""
    return solve_core(store)


@router.get(
    "/api/projects/{project_id}/views/pfd.svg",
    response_class=Response,
    responses=_SVG_RESPONSES,
)
def pfd_svg_project(store: Annotated[DbProjectStore, Depends(project_store)]) -> Response:
    """The project's PFD with layout.pfd placement overrides."""
    return pfd_svg_core(store)


@router.get(
    "/api/projects/{project_id}/views/pid.svg",
    response_class=Response,
    responses=_SVG_RESPONSES,
)
def pid_svg_project(store: Annotated[DbProjectStore, Depends(project_store)]) -> Response:
    """The project's P&ID: builder + all rules at a fixed point."""
    return pid_svg_core(store)


@router.post("/api/projects/{project_id}/route")
def route_project(store: Annotated[DbProjectStore, Depends(project_store)]) -> PipingNetwork:
    """Route the project's P&ID through its layout.plot placements."""
    return route_core(store)


@router.get(
    "/api/projects/{project_id}/views/plot.svg",
    response_class=Response,
    responses=_SVG_RESPONSES,
)
def plot_svg_project(store: Annotated[DbProjectStore, Depends(project_store)]) -> Response:
    """Top view of the project's routed piping, plan north up."""
    return plot_svg_core(store)


@router.get("/api/projects/{project_id}/export/sheet", response_class=Response)
def export_sheet_project(
    format: str, store: Annotated[DbProjectStore, Depends(project_store)], scope: str = "all"
) -> Response:
    """Export the project's solved sheet; 422 naming the allowed values on a bad format/scope."""
    return export_sheet_core(store, format, scope)


@router.get("/api/projects/{project_id}/views/iso")
def iso_lines_project(store: Annotated[DbProjectStore, Depends(project_store)]) -> list[str]:
    """The project's routed line numbers (empty when none)."""
    return iso_lines_core(store)


@router.get(
    "/api/projects/{project_id}/views/iso/{line_number}.svg",
    response_class=Response,
    responses=_SVG_RESPONSES,
)
def iso_svg_project(line_number: str, store: Annotated[DbProjectStore, Depends(project_store)]) -> Response:
    """Fabrication isometric of the project for one routed line."""
    return iso_svg_core(store, line_number)


@router.get("/api/projects/{project_id}/views/iso/{line_number}.json", response_model=IsoSheet)
def iso_sheet_project(line_number: str, store: Annotated[DbProjectStore, Depends(project_store)]) -> IsoSheet:
    """IsoSheet of the project for one routed line."""
    return iso_sheet_core(store, line_number)


@router.put("/api/projects/{project_id}/layout/iso/{key}")
def place_iso_project(
    key: str, pos: XY, store: Annotated[DbProjectStore, Depends(project_store)]
) -> dict[str, XY]:
    """Store a layout.iso placement for the project."""
    return place_iso_core(store, key, pos)


@router.put("/api/projects/{project_id}/layout/plot/{tag}")
def place_plot_project(
    tag: str, pos: Vec3, store: Annotated[DbProjectStore, Depends(project_store)]
) -> Layout:
    """Place project equipment on the plot plan and return the layout."""
    project = store.get()
    _require_tag(project, tag)
    project.layout.plot[tag] = pos
    store.put(project)
    return project.layout


def _require_tag(project: Project, tag: str) -> None:
    """P3-01 x-check: a placement for a tag not in the project is 409 (the
    legacy unscoped routes stay permissive for the current frontend)."""
    if tag not in {unit.tag for unit in project.flowsheet.units}:
        raise HTTPException(status_code=409, detail=f"unknown unit tag {tag!r}")


@router.put("/api/projects/{project_id}/layout/{view}/{tag}")
def place_project(
    view: Literal["pfd", "pid"], tag: str, pos: XY, store: Annotated[DbProjectStore, Depends(project_store)]
) -> Layout:
    """Place a pfd/pid element of the project and return the layout."""
    project = store.get()
    _require_tag(project, tag)
    getattr(project.layout, view)[tag] = pos
    store.put(project)
    return project.layout


@router.post("/api/projects/{project_id}/agent")
def agent_message_project(
    req: AgentRequest, store: Annotated[DbProjectStore, Depends(project_store)]
) -> Response:
    """One agent turn on the project, streamed as SSE."""
    return agent_message_core(store, req)


@router.get("/api/projects/{project_id}/agent")
def agent_conversations_project(
    store: Annotated[DbProjectStore, Depends(project_store)],
) -> dict[str, list[str]]:
    """The project's stored conversation ids."""
    return agent_conversations_core(store)


@router.get("/api/projects/{project_id}/agent/{conversation_id}")
def agent_transcript_project(
    conversation_id: str, store: Annotated[DbProjectStore, Depends(project_store)]
) -> dict[str, object]:
    """One stored conversation's history."""
    return agent_transcript_core(store, conversation_id)


@router.delete("/api/projects/{project_id}/agent/{conversation_id}")
def agent_delete_project(
    conversation_id: str, store: Annotated[DbProjectStore, Depends(project_store)]
) -> dict[str, str]:
    """Forget one stored conversation of the project."""
    return agent_conversation_delete_core(store, conversation_id)
