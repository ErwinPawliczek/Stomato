"""GET /api/views/pid.svg (spec B-04).

Serves the same P&ID chain as the S-35 CLI demo: solve the current project
(seam shared with POST /api/solve), then ``pipeline.build_pid`` — sizers,
bare P&ID (S-33), every registered pid_rule to a fixed point — and render
(S-18) with the project's ``layout.pid`` placements applied on top. With an
empty ``layout.pid`` the response is byte-identical to the CLI demo's
out/pid.svg.

Spec P3-01: :func:`pid_svg_core` takes the store, so routes_projects.py can
register the project-scoped twin; the legacy unscoped route is a deprecated
alias bound to the ``default`` project.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from ngdesign import pipeline
from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.render.pid_svg import render_pid_svg

router = APIRouter()

_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


def pid_svg_core(store: ProjectStore) -> Response:
    """P&ID of the project: builder + all rules at a fixed point."""
    project = store.get()
    from ngdesign.api.routes_solve import solve_core

    # Sizers mutate the flowsheet with datasheets: build on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    pid = pipeline.build_pid(solve_core(store).model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
    svg = render_pid_svg(pid, project.layout.pid)
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/views/pid.svg", response_class=Response, responses=_SVG, deprecated=True)
def pid_svg(store: Annotated[ProjectStore, Depends(default_project_store)]) -> Response:
    """P&ID of the default project: builder + all rules at a fixed point."""
    return pid_svg_core(store)
