"""POST /api/solve (spec B-02) — the HTTP surface over the shared solve path.

Spec B-08 moved the solve logic, its project-hash helper and the plugin/semantic
error types into ``ngdesign.agent.engine``, so this route and the agent's
``solve`` tool are ONE solve path. What stays here: the HTTP mapping (missing
plugin -> 501, semantically invalid project -> 422) and the route's own cache
dict — a locked test (tests/api/test_solve_errors.py) monkeypatches
``routes_solve._cache`` for isolation, so the route keeps that seam and injects
it into the shared helper. Outside that test the attribute IS the engine's
cache, so the route and the agent share one cache.

Spec P3-01 adds the project-scoped twin (registered in routes_projects.py):
:func:`solve_core` is the single implementation; the legacy unscoped route is a
deprecated alias bound to the ``default`` project.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ngdesign.agent import engine
from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.contracts import SolvedFlowsheet

router = APIRouter()

#: project hash -> solved result (spec B-02: "cache by project hash"). Injected
#: into the shared solve helper; a locked test monkeypatches this attribute.
_cache: dict[str, SolvedFlowsheet] = engine._cache  # the engine's own cache: one cache in production

# The shared helpers, re-exported under their historical names.
project_hash = engine.project_hash
first_missing_unit_kind = engine.first_missing_unit_kind


def solve_core(store: ProjectStore) -> SolvedFlowsheet:
    """Solve the project behind ``store`` (the one implementation; the legacy
    route and the project-scoped twin both call this)."""
    try:
        return engine.solve_project(store.get(), cache=_cache)
    except engine.UnknownPluginError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except engine.InvalidProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/solve", deprecated=True)
def solve(store: Annotated[ProjectStore, Depends(default_project_store)]) -> SolvedFlowsheet:
    """Solve the default project; 501 naming the kind when a unit is missing."""
    return solve_core(store)


__all__ = ["first_missing_unit_kind", "project_hash", "router", "solve", "solve_core"]
