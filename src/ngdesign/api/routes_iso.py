"""Isometric view API (spec B-06).

Serves the S-19 fabrication isometric per routed line, exactly the S-35 CLI
chain at the iso stage: solve -> sizers -> P&ID builder -> every registered
pid_rule to a fixed point (``pipeline.build_pid``) -> S-21 routing
(``pipeline.route``, with the project's ``layout.plot`` placements) ->
``registry.create("iso_renderer", "svg").render(line, pid)`` for each routed
line. With an empty ``layout.iso`` every served ``.svg`` is byte-identical to
the CLI demo's ``out/iso_NN_<line>.svg``.

``layout.iso`` placement overrides are 2D screen-space shifts (dx, dy)
applied to a tagged SVG group after projection — the draft's recommended
option (a), same ``{"x", "y"}`` payload shape as B-04's ``layout.pid``. The
locked ``Layout`` contract carries only ``pfd``/``pid``/``plot``, so the
placements live here (keyed by project id since spec P3-01) until a contract
change adds ``Layout.iso`` — the same module-state pattern as the solve cache
in routes_solve. Overrides for keys that match no data-tag group are ignored
by the renderer (no-op).

Spec P3-01: the ``*_core`` handlers take the store, so routes_projects.py can
register the project-scoped twins; the legacy unscoped routes are deprecated
aliases bound to the ``default`` project.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from ngdesign import pipeline, registry
from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.contracts import PID, XY, IsoSheet, PipingNetwork, RoutedLine
from ngdesign.store import DbProjectStore

router = APIRouter()

_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}

#: project id -> (data-tag -> screen-space shift); see the module docstring for
#: why this lives here rather than in the locked Layout contract.
_iso_placements: dict[str, dict[str, XY]] = {}


def _placements_for(project_id: str) -> dict[str, XY]:
    return _iso_placements.setdefault(project_id, {})


def _find_line(net: PipingNetwork, line_number: str) -> RoutedLine:
    line = next((ln for ln in net.lines if ln.line_number == line_number), None)
    if line is None:
        raise HTTPException(status_code=404, detail=f"no routed line {line_number!r}")
    return line


def _routed_for(store: ProjectStore) -> tuple[PID, PipingNetwork]:
    """Build and route the project's P&ID through pipeline (P0-03)."""
    from ngdesign.api.routes_solve import solve_core

    # Sizers mutate the flowsheet with datasheets: build on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    pid = pipeline.build_pid(solve_core(store).model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
    # Placements for tags that left the P&ID are ignored, like layout.pfd/pid.
    project = store.get()
    tags = {eq.tag for eq in pid.equipment}
    layout = {tag: pos for tag, pos in project.layout.plot.items() if tag in tags}
    return pid, pipeline.route(pid, layout)


def iso_lines_core(store: ProjectStore) -> list[str]:
    """Routed line numbers available for isometric views (empty when none)."""
    _, net = _routed_for(store)
    return [line.line_number for line in net.lines]


@router.get("/api/views/iso", deprecated=True)
def iso_lines(store: Annotated[ProjectStore, Depends(default_project_store)]) -> list[str]:
    """Routed line numbers of the default project (empty when none)."""
    return iso_lines_core(store)


def iso_svg_core(store: DbProjectStore, line_number: str) -> Response:
    """Fabrication isometric for one routed line, layout.iso applied."""
    pid, net = _routed_for(store)
    line = _find_line(net, line_number)
    placements = {key: (pos.x, pos.y) for key, pos in _placements_for(store.project_id).items()}
    sheet: IsoSheet = registry.create("iso_renderer", "svg").render(line, pid, placements=placements)
    return Response(content=sheet.svg, media_type="image/svg+xml")


@router.get("/api/views/iso/{line_number}.svg", response_class=Response, responses=_SVG, deprecated=True)
def iso_svg(line_number: str, store: Annotated[DbProjectStore, Depends(default_project_store)]) -> Response:
    """Fabrication isometric of the default project for one routed line."""
    return iso_svg_core(store, line_number)


def iso_sheet_core(store: ProjectStore, line_number: str) -> IsoSheet:
    """IsoSheet for one routed line: title block, BOM, cut list, totals."""
    pid, net = _routed_for(store)
    sheet: IsoSheet = registry.create("iso_renderer", "svg").render(_find_line(net, line_number), pid)
    return sheet


@router.get("/api/views/iso/{line_number}.json", response_model=IsoSheet, deprecated=True)
def iso_sheet(line_number: str, store: Annotated[ProjectStore, Depends(default_project_store)]) -> IsoSheet:
    """IsoSheet of the default project for one routed line."""
    return iso_sheet_core(store, line_number)


def place_iso_core(store: DbProjectStore, key: str, pos: XY) -> dict[str, XY]:
    """Store a layout.iso placement for the project; the iso views apply it on
    the next render."""
    placements = _placements_for(store.project_id)
    placements[key] = pos
    return dict(placements)


@router.put("/api/project/layout/iso/{key}", deprecated=True)
def place_iso(
    key: str, pos: XY, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> dict[str, XY]:
    """Store a layout.iso placement on the default project."""
    return place_iso_core(store, key, pos)
