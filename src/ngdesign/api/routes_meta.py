"""GET /api/meta — plugin registry metadata (wave-2 surfacing spec).

Returns the engine's registered plugin names per registry kind, e.g.
``{"thermo": ["nrtl", "pr", "pr78", "srk"], "unit": ["cooler", ...], ...}``.
This is the discovery seam the frontend needs to enumerate what the solver
can consume (thermo selector, add-unit palette); until now registry
discovery was internal-only (surfacing map art_uNGwXtkc §3). Read-only,
stateless, additive: no project state, no solver involvement.
"""

from __future__ import annotations

from fastapi import APIRouter

from ngdesign import registry

router = APIRouter()


@router.get("/api/meta")
def meta() -> dict[str, list[str]]:
    """List registered plugin names for every registry kind."""
    return {kind: registry.available(kind) for kind in registry.KINDS}
