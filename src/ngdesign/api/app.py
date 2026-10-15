"""FastAPI app. Route signatures are the frontend contract: changing them regenerates openapi.json,
and CI fails until frontend/src/api/schema.d.ts is regenerated too.

Run: uv run uvicorn ngdesign.api.app:app --reload --port 8000
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ngdesign.api.routes_export import router as export_router
from ngdesign.api.routes_iso import router as iso_router
from ngdesign.api.routes_meta import router as meta_router
from ngdesign.api.routes_pid import router as pid_router
from ngdesign.api.routes_plot import router as plot_router
from ngdesign.api.routes_solve import router as solve_router
from ngdesign.api.routes_views import router as views_router
from ngdesign.contracts import XY, Layout, Project, Vec3
from ngdesign.flowsheets import slice as slice_fs

app = FastAPI(title="ngdesign", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(plot_router)
app.include_router(pid_router)
# Registered with the other routers (before app.py's own layout catch-all) so
# the iso placement PUT matches /api/project/layout/iso/{key} first.
app.include_router(iso_router)
app.include_router(solve_router)
app.include_router(views_router)
app.include_router(export_router)
app.include_router(meta_router)

_state: dict[str, Project] = {}


def _project() -> Project:
    if "p" not in _state:
        _state["p"] = Project(name="slice", flowsheet=slice_fs.build())
    return _state["p"]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/project")
def get_project() -> Project:
    return _project()


@app.put("/api/project")
def put_project(project: Project) -> Project:
    _state["p"] = project
    return project


@app.post("/api/project/reset")
def reset_project() -> Project:
    _state.pop("p", None)
    return _project()


# The plot route must be registered before the {view}/{tag} catch-all:
# Starlette matches in registration order, and the catch-all's Literal["pfd", "pid"]
# would 422 every plot placement (the XY body also rejects Vec3's z).
@app.put("/api/project/layout/plot/{tag}")
def place_plot(tag: str, pos: Vec3) -> Layout:
    p = _project()
    p.layout.plot[tag] = pos
    return p.layout


@app.put("/api/project/layout/{view}/{tag}")
def place(view: Literal["pfd", "pid"], tag: str, pos: XY) -> Layout:
    p = _project()
    getattr(p.layout, view)[tag] = pos
    return p.layout
