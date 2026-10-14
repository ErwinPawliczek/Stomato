"""POST /api/solve (spec B-02).

Solves the current project with the ``pr`` thermo package and the
``sequential_modular`` solver through the registry seam — the same engine path
as the S-35 CLI slice demo. Results are cached by project hash so repeated
solves of an unchanged project return instantly.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException

from ngdesign import registry
from ngdesign.contracts import Project, SolvedFlowsheet

router = APIRouter()

#: project hash -> solved result (spec B-02: "cache by project hash").
_cache: dict[str, SolvedFlowsheet] = {}


def project_hash(project: Project) -> str:
    """Stable content hash of the full project model."""
    return hashlib.sha256(project.model_dump_json().encode("utf-8")).hexdigest()


def first_missing_unit_kind(project: Project) -> str | None:
    """First unit kind in the flowsheet with no registered plugin, if any."""
    known = set(registry.available("unit"))
    for spec in project.flowsheet.units:
        if spec.kind not in known:
            return spec.kind
    return None


@router.post("/api/solve")
def solve() -> SolvedFlowsheet:
    """Solve the current project; 501 naming the kind when a unit is missing."""
    # Late import: app.py owns the current project and registers this router,
    # so a module-level import would be circular.
    from ngdesign.api.app import _project

    project = _project()
    missing = first_missing_unit_kind(project)
    if missing is not None:
        raise HTTPException(status_code=501, detail=f"unit kind {missing!r} has no registered plugin")
    key = project_hash(project)
    if key not in _cache:
        thermo = registry.create("thermo", "pr")
        try:
            _cache[key] = registry.create("solver", "sequential_modular").solve(project.flowsheet, thermo)
        except ValueError as exc:
            # Semantically invalid project the PUT-time contracts cannot reject:
            # declared ports and feed specs are only known to the plugins at
            # solve time (e.g. a stream naming a port the unit does not have).
            # That is client error (422), never a 500.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _cache[key]
