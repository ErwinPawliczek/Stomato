"""GET /api/export/sheet (B-07 addendum).

Serves the engineering sheet — stream table and equipment datasheets — as a
CSV download or semantic HTML. The export is a pure function of the
:class:`SolvedFlowsheet` that ``POST /api/solve`` returns, so values are
byte-equal to the CLI demo's ``index.html`` stream table: both go through
``ngdesign.export``, which formats every cell with the CLI's own ``_cell``.

The datasheet block renders whatever ``solved.datasheets`` carries — today the
solve seam does not attach datasheets (sizing is a CLI wiring stage), so the
section is header-only until a solve that carries them; the contract-field
headers keep the export checkable against the solve payload either way.

Spec P3-01: :func:`export_sheet_core` takes the store, so routes_projects.py
can register the project-scoped twin; the legacy unscoped route is a deprecated
alias bound to the ``default`` project.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.export import coerce_scope, sheet_csv, sheet_html

router = APIRouter()

_FORMATS: tuple[str, ...] = ("csv", "html")


def export_sheet_core(store: ProjectStore, format: str, scope: str = "all") -> Response:
    """Export the project's solved sheet; 422 naming the allowed values on a bad format/scope."""
    if format not in _FORMATS:
        raise HTTPException(status_code=422, detail=f"format must be one of: {', '.join(_FORMATS)}")
    try:
        scope_arg = coerce_scope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    from ngdesign.api.routes_solve import solve_core

    solved = solve_core(store)  # cached by project hash; re-solves only after an edit

    if format == "csv":
        return Response(
            content=sheet_csv(solved, scope_arg),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="sheet.csv"'},
        )
    return Response(content=sheet_html(solved, scope_arg), media_type="text/html; charset=utf-8")


@router.get("/api/export/sheet", deprecated=True)
def export_sheet(
    format: str, store: Annotated[ProjectStore, Depends(default_project_store)], scope: str = "all"
) -> Response:
    """Export the default project's solved sheet."""
    return export_sheet_core(store, format, scope)
