"""FastAPI app. Route signatures are the frontend contract: changing them regenerates openapi.json,
and CI fails until frontend/src/api/schema.d.ts is regenerated too.

Run: uv run uvicorn ngdesign.api.app:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from ngdesign.api.routes_solve import router as solve_router
from ngdesign.contracts import XY, Layout, Project, Vec3
from ngdesign.flowsheets import slice as slice_fs

app = FastAPI(title="ngdesign", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(solve_router)

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


@app.put("/api/project/layout/{view}/{tag}")
def place(view: Literal["pfd", "pid"], tag: str, pos: XY) -> Layout:
    p = _project()
    getattr(p.layout, view)[tag] = pos
    return p.layout


@app.put("/api/project/layout/plot/{tag}")
def place_plot(tag: str, pos: Vec3) -> Layout:
    p = _project()
    p.layout.plot[tag] = pos
    return p.layout


_SVG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}


@app.get("/api/views/{view}.svg", response_class=Response, responses=_SVG)
def view_svg(view: Literal["pfd", "pid", "plot"]) -> Response:
    """Implemented by specs B-03/B-04/B-05. Returns SVG text with data-tag attributes on elements."""
    raise HTTPException(status_code=501, detail=f"{view} renderer not wired yet")
