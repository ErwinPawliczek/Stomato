"""Plot plan + routing API (spec B-05).

POST /api/route and GET /api/views/plot.svg both serve the S-21 orthogonal
router's output for the current project: the same engine chain as
GET /api/views/pid.svg (solve seam shared with POST /api/solve, then
``pipeline.build_pid`` — sizers, P&ID builder, every registered pid_rule to a
fixed point) routed through the project's ``layout.plot`` placements. With an
empty ``layout.plot`` the routing is exactly the S-35 CLI demo's
``route(pid, layout={})`` — same router, same lines, same geometry — so both
routes render the routing itself, not a separate model. Moving equipment via
PUT /api/project/layout/plot/{tag} re-routes on the next request: routed
lengths follow the equipment.

POST /api/route returns the routed network as JSON: per line the ordered
components (mm centreline geometry, elbows, flanges) plus the equipment
envelopes. GET /api/views/plot.svg draws the same network as a plan view
(``ngdesign.render.plot_svg``): envelope footprints and each line's
centreline projected onto the x-y plane (north up), every equipment and line
wrapped in a ``data-tag`` group like the pfd/pid views.

A project whose unit kind has no registered plugin cannot be solved, so it
cannot be routed either: both routes answer 501 naming the kind, exactly like
POST /api/solve. Layout placements for tags that are no longer in the P&ID
are ignored (same policy as the pfd/pid views).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from ngdesign import pipeline
from ngdesign.contracts import PipingNetwork
from ngdesign.render.plot_svg import render_plot_svg

router = APIRouter()

_SVG_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


@router.post("/api/route")
def route() -> PipingNetwork:
    """Route the current project's P&ID through the layout.plot placements."""
    # Late imports: app.py owns the current project and registers this router,
    # so a module-level import would be circular (same pattern as routes_solve).
    from ngdesign.api.app import _project
    from ngdesign.api.routes_solve import solve

    project = _project()
    # Sizers mutate the flowsheet with datasheets: build on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    pid = pipeline.build_pid(solve().model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
    # Placements for tags that left the P&ID are ignored, like layout.pfd/pid.
    tags = {eq.tag for eq in pid.equipment}
    layout = {tag: pos for tag, pos in project.layout.plot.items() if tag in tags}
    return pipeline.route(pid, layout)


@router.get("/api/views/plot.svg", response_class=Response, responses=_SVG_RESPONSES)
def plot_svg() -> Response:
    """Top view of the current project's routed piping, plan north up."""
    return Response(content=render_plot_svg(route()), media_type="image/svg+xml")
