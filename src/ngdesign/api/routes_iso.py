"""Isometric view API (spec B-06).

Serves the S-19 fabrication isometric per routed line, exactly the S-35 CLI
chain at the iso stage: solve -> sizers -> P&ID builder -> every registered
pid_rule to a fixed point -> S-21 routing (with the project's ``layout.plot``
placements) -> ``registry.create("iso_renderer", "svg").render(line, pid)``
for each routed line. With an empty ``layout.iso`` every served ``.svg`` is
byte-identical to the CLI demo's ``out/iso_NN_<line>.svg``.

``layout.iso`` placement overrides are 2D screen-space shifts (dx, dy)
applied to a tagged SVG group after projection — the draft's recommended
option (a), same ``{"x", "y"}`` payload shape as B-04's ``layout.pid``. The
locked ``Layout`` contract carries only ``pfd``/``pid``/``plot``, so the
placements live here until a contract change adds ``Layout.iso`` — the same
module-state pattern as the solve cache in routes_solve. Overrides for keys
that match no data-tag group are ignored by the renderer (no-op).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ngdesign import registry
from ngdesign.contracts import PID, XY, IsoSheet, PipingNetwork, RoutedLine

router = APIRouter()

_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}

#: data-tag -> screen-space shift; see the module docstring for why this
#: lives here rather than in the locked Layout contract.
_iso_placements: dict[str, XY] = {}


def _routed() -> tuple[PID, PipingNetwork]:
    """The S-35 chain through routing: solve -> sizers -> builder -> rules -> S-21."""
    # Late imports: app.py owns the current project and registers this router,
    # so a module-level import would be circular (same pattern as routes_solve).
    from ngdesign.api.app import _project
    from ngdesign.api.routes_solve import solve
    from ngdesign.cli import _apply_rules, _rule_set, _run_sizers

    project = _project()
    # Sizers mutate the flowsheet with datasheets: run them on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    solved = _run_sizers(solve().model_copy(deep=True))
    pid = registry.create("pid_builder", "default").build(solved)
    pid = _apply_rules(pid, _rule_set(solved))
    # Placements for tags that left the P&ID are ignored, like layout.pfd/pid.
    tags = {eq.tag for eq in pid.equipment}
    layout = {tag: pos for tag, pos in project.layout.plot.items() if tag in tags}
    net: PipingNetwork = registry.create("router", "orthogonal").route(pid, layout)
    return pid, net


def _find_line(net: PipingNetwork, line_number: str) -> RoutedLine:
    line = next((ln for ln in net.lines if ln.line_number == line_number), None)
    if line is None:
        raise HTTPException(status_code=404, detail=f"no routed line {line_number!r}")
    return line


@router.get("/api/views/iso")
def iso_lines() -> list[str]:
    """Routed line numbers available for isometric views (empty when none)."""
    return [line.line_number for line in _routed()[1].lines]


@router.get("/api/views/iso/{line_number}.svg", response_class=Response, responses=_SVG)
def iso_svg(line_number: str) -> Response:
    """Fabrication isometric for one routed line, layout.iso applied."""
    pid, net = _routed()
    line = _find_line(net, line_number)
    placements = {key: (pos.x, pos.y) for key, pos in _iso_placements.items()}
    sheet: IsoSheet = registry.create("iso_renderer", "svg").render(line, pid, placements=placements)
    return Response(content=sheet.svg, media_type="image/svg+xml")


@router.get("/api/views/iso/{line_number}.json", response_model=IsoSheet)
def iso_sheet(line_number: str) -> IsoSheet:
    """IsoSheet for one routed line: title block, BOM, cut list, totals."""
    pid, net = _routed()
    return registry.create("iso_renderer", "svg").render(_find_line(net, line_number), pid)


@router.put("/api/project/layout/iso/{key}")
def place_iso(key: str, pos: XY) -> dict[str, XY]:
    """Store a layout.iso placement; the iso views apply it on the next render."""
    _iso_placements[key] = pos
    return dict(_iso_placements)
