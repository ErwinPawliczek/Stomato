"""GET /api/views/pid.svg (spec B-04).

Serves the same P&ID chain as the S-35 CLI demo: solve the current project
(seam shared with POST /api/solve), run the sizers, build the bare P&ID
(S-33), apply every registered pid_rule to a fixed point, then render (S-18)
with the project's ``layout.pid`` placements applied on top. With an empty
``layout.pid`` the response is byte-identical to the CLI demo's out/pid.svg.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from ngdesign import registry
from ngdesign.cli import _apply_rules, _rule_set, _run_sizers
from ngdesign.render.pid_svg import render_pid_svg

router = APIRouter()

_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


@router.get("/api/views/pid.svg", response_class=Response, responses=_SVG)
def pid_svg() -> Response:
    """P&ID of the current project: builder + all rules at a fixed point."""
    # Late imports: app.py owns the current project and registers this router,
    # so a module-level import would be circular.
    from ngdesign.api.app import _project
    from ngdesign.api.routes_solve import solve

    project = _project()
    # Sizers mutate the flowsheet with datasheets: run them on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    solved = _run_sizers(solve().model_copy(deep=True))
    pid = registry.create("pid_builder", "default").build(solved)
    rules = _rule_set(solved)
    pid = _apply_rules(pid, rules)
    svg = render_pid_svg(pid, project.layout.pid)
    return Response(content=svg, media_type="image/svg+xml")
