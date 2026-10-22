"""GET /api/meta — plugin registry metadata (wave-2 surfacing spec).

Returns the engine's registered plugin names per registry kind, e.g.
``{"thermo": ["nrtl", "pr", "pr78", "srk"], "unit": ["cooler", ...], ...}``.
This is the discovery seam the frontend needs to enumerate what the solver
can consume (thermo selector, add-unit palette); until now registry
discovery was internal-only (surfacing map art_uNGwXtkc §3). Read-only,
stateless, additive: no project state, no solver involvement.

Spec T-08 adds the thermo surfaces on the same module (they are registry
metadata, not solver state): ``GET /api/thermo/recommend`` returns the model
advisor's ranked property methods for the current project — the same payload
the agent's ``recommend_thermo`` tool returns, through the same
``advisor.payload`` serialisation, so the two surfaces cannot drift — and
``GET /api/thermo/models`` lists every catalogue row with its ``selectable``
flag (issue #154): ``experimental`` rows stay registered and listed but are
marked ``selectable: false`` with the row's own refusal reason (status +
``l0_note``/references), so a flowsheet cannot pick a model that fails at its
first flash.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ngdesign import registry
from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.thermo import advisor
from ngdesign.thermo.catalogue import load_catalogue

router = APIRouter()


@router.get("/api/meta")
def meta() -> dict[str, list[str]]:
    """List registered plugin names for every registry kind."""
    return {kind: registry.available(kind) for kind in registry.KINDS}


@router.get("/api/thermo/recommend")
def thermo_recommend(
    store: Annotated[ProjectStore, Depends(default_project_store)],
) -> dict[str, Any]:
    """Ranked property-method recommendations for the current project (spec T-08)."""
    result: dict[str, Any] = advisor.payload(store.get().flowsheet)
    return result


@router.get("/api/thermo/models")
def thermo_models() -> dict[str, Any]:
    """Every catalogue row with its selectable flag and refusal reason (issue #154)."""
    models: list[dict[str, Any]] = []
    for row_id in sorted(load_catalogue()):
        row = load_catalogue()[row_id]
        selectable = row.status != "experimental"
        entry: dict[str, Any] = {
            "id": row.id,
            "name": row.name,
            "family": row.family,
            "status": row.status,
            "selectable": selectable,
        }
        if not selectable:
            reason = "status: experimental"
            if row.l0_note:
                reason += f" — {row.l0_note}"
            if row.references:
                reason += f" — see {row.references[0]}"
            entry["refusal_reason"] = reason
        models.append(entry)
    return {"models": models}
