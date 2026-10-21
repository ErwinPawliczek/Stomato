"""POST /api/solve (spec B-02) — the HTTP surface over the shared solve path.

Spec B-08 moved the solve logic, its project-hash helper and the plugin/semantic
error types into ``ngdesign.agent.engine``, so this route and the agent's
``solve`` tool are ONE solve path. What stays here: the HTTP mapping (missing
plugin -> 501, semantically invalid project -> 422) and the route's own cache
dict — a locked test (tests/api/test_solve_errors.py) monkeypatches
``routes_solve._cache`` for isolation, so the route keeps that seam and injects
it into the shared helper. Outside that test the attribute IS the engine's
cache, so the route and the agent share one cache.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ngdesign.agent import engine
from ngdesign.contracts import SolvedFlowsheet

router = APIRouter()

#: project hash -> solved result (spec B-02: "cache by project hash"). Injected
#: into the shared solve helper; a locked test monkeypatches this attribute.
_cache: dict[str, SolvedFlowsheet] = engine._cache  # the engine's own cache: one cache in production

# The shared helpers, re-exported under their historical names.
project_hash = engine.project_hash
first_missing_unit_kind = engine.first_missing_unit_kind


@router.post("/api/solve")
def solve() -> SolvedFlowsheet:
    """Solve the current project; 501 naming the kind when a unit is missing."""
    # Late import: app.py owns the current project and registers this router,
    # so a module-level import would be circular.
    from ngdesign.api.app import _project

    try:
        return engine.solve_project(_project(), cache=_cache)
    except engine.UnknownPluginError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except engine.InvalidProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["first_missing_unit_kind", "project_hash", "router", "solve"]
