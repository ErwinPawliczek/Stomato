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
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from ngdesign.render.pfd_svg import render_pfd_svg

router = APIRouter()

_SVG_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


@router.get("/api/views/pfd.svg", response_class=Response, responses=_SVG_RESPONSES)
def pfd_svg() -> Response:
    """Render the current project's PFD with layout.pfd placement overrides."""
    # Late imports: app.py owns the current project and registers this router,
    # so a module-level import would be circular (same pattern as routes_solve).
    from ngdesign.api.app import _project
    from ngdesign.api.routes_solve import solve

    project = _project()
    solved = solve()  # cached by project hash; re-solves only after an edit
    svg = render_pfd_svg(solved, overrides=project.layout.pfd)
    return Response(content=svg, media_type="image/svg+xml")
