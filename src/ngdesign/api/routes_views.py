"""GET /api/views/pfd.svg (spec B-03).

Serves the S-22 PFD renderer's output for the current project, applying the
project's ``layout.pfd`` placement overrides: a placed unit renders at its
stored centre position, unplaced units auto-layout. Without overrides the
response is byte-for-byte the SVG the CLI demo writes to ``out/pfd.svg`` for
the sample slice — both go through the same renderer on the same solved
flowsheet (POST /api/solve seam, spec B-02).

A project whose unit kind has no registered plugin cannot be solved, so it
cannot be rendered either: the route answers 501 naming the kind, exactly
like POST /api/solve.

Spec P3-01: :func:`pfd_svg_core` takes the store, so routes_projects.py can
register the project-scoped twin; the legacy unscoped route is a deprecated
alias bound to the ``default`` project.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.render.pfd_svg import render_pfd_svg

router = APIRouter()

_SVG_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


def pfd_svg_core(store: ProjectStore) -> Response:
    """Render the project's PFD with layout.pfd placement overrides."""
    project = store.get()
    # Late import: the solve seam lives in routes_solve (module-level import
    # would make routes_solve's router registration order load-bearing here).
    from ngdesign.api.routes_solve import solve_core

    solved = solve_core(store)  # cached by project hash; re-solves only after an edit
    svg = render_pfd_svg(solved, overrides=project.layout.pfd)
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/views/pfd.svg", response_class=Response, responses=_SVG_RESPONSES, deprecated=True)
def pfd_svg(store: Annotated[ProjectStore, Depends(default_project_store)]) -> Response:
    """Render the default project's PFD with layout.pfd placement overrides."""
    return pfd_svg_core(store)
