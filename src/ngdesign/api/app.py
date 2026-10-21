"""FastAPI app. Route signatures are the frontend contract: changing them regenerates openapi.json,
and CI fails until frontend/src/api/schema.d.ts is regenerated too.

Run: uv run uvicorn ngdesign.api.app:app --reload --port 8000

Spec P3-01: every route is project-scoped and owner-checked. The legacy
unscoped routes (/api/project, POST /api/solve, the views, ...) stay working
byte-for-byte for the current frontend as deprecated aliases bound to the
caller's ``default`` project (created on first use from the sample slice) —
see deps.py. Auth is an app-level dependency (auth.py): STOMATO_API_TOKENS unset
means open (local dev), set means a bearer token maps every request to an owner.
The database comes from STOMATO_DATABASE_URL (store/db.py); init_db() runs in
the lifespan, and the store also self-initializes lazily so a bare TestClient
works without lifespan events.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ngdesign.api import auth
from ngdesign.api.deps import default_project_store, slice_project
from ngdesign.api.routes_agent import router as agent_router
from ngdesign.api.routes_export import router as export_router
from ngdesign.api.routes_iso import router as iso_router
from ngdesign.api.routes_meta import router as meta_router
from ngdesign.api.routes_pid import router as pid_router
from ngdesign.api.routes_plot import router as plot_router
from ngdesign.api.routes_projects import router as projects_router
from ngdesign.api.routes_solve import router as solve_router
from ngdesign.api.routes_views import router as views_router
from ngdesign.contracts import XY, Layout, Project, Vec3
from ngdesign.store import (
    DbProjectStore,
    ProjectConflict,
    ProjectForbidden,
    ProjectNotFound,
    init_db,
)

#: Allowed browser origins (spec P3-01): comma-separated STOMATO_CORS_ORIGINS,
#: default the Vite dev server; "*" is never accepted.
CORS_ORIGINS_ENV = "STOMATO_CORS_ORIGINS"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


def cors_origins() -> list[str]:
    """The configured origins; a '*' entry is a config error, not a wildcard."""
    raw = os.environ.get(CORS_ORIGINS_ENV)
    origins = [o.strip() for o in raw.split(",") if o.strip()] if raw else list(DEFAULT_CORS_ORIGINS)
    if "*" in origins:
        raise ValueError(f"{CORS_ORIGINS_ENV} must list explicit origins; '*' is not allowed")
    return origins


#: The legacy unscoped routes (deprecated aliases bound to the default project).
legacy_router = APIRouter()


def create_app() -> FastAPI:
    """The FastAPI app: routers, auth dependency, CORS, store error mapping."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db()
        auth.auth_state()  # logs the auth mode (open vs N tokens) once at startup
        yield

    application = FastAPI(
        title="ngdesign",
        version="0.1.0",
        lifespan=lifespan,
        # Every /api route is owner-checked; auth.py exempts /api/health itself.
        dependencies=[Depends(auth.current_owner)],
    )
    application.add_middleware(
        CORSMiddleware, allow_origins=cors_origins(), allow_methods=["*"], allow_headers=["*"]
    )

    application.include_router(projects_router)
    application.include_router(plot_router)
    application.include_router(pid_router)
    # Registered with the other routers (before app.py's own layout catch-all) so
    # the iso placement PUT matches /api/project/layout/iso/{key} first.
    application.include_router(iso_router)
    application.include_router(solve_router)
    application.include_router(views_router)
    application.include_router(export_router)
    application.include_router(meta_router)
    application.include_router(agent_router)
    # Last: its /api/project/layout/{view}/{tag} catch-all must not shadow the iso PUT.
    application.include_router(legacy_router)

    @application.exception_handler(ProjectNotFound)
    def _not_found(_: Request, exc: ProjectNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(ProjectForbidden)
    def _forbidden(_: Request, exc: ProjectForbidden) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @application.exception_handler(ProjectConflict)
    def _conflict(_: Request, exc: ProjectConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    return application


@legacy_router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@legacy_router.get("/api/project", deprecated=True)
def get_project(store: Annotated[DbProjectStore, Depends(default_project_store)]) -> Project:
    """The default project (deprecated: GET /api/projects/{id})."""
    return store.get()


@legacy_router.put("/api/project", deprecated=True)
def put_project(
    project: Project, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> Project:
    """Replace the default project's body (deprecated: PUT /api/projects/{id})."""
    store.put(project)
    return project


@legacy_router.post("/api/project/reset", deprecated=True)
def reset_project(store: Annotated[DbProjectStore, Depends(default_project_store)]) -> Project:
    """Reset the default project to the sample slice (deprecated: PUT /api/projects/{id})."""
    store.put(slice_project())
    return store.get()


# The plot route must be registered before the {view}/{tag} catch-all:
# Starlette matches in registration order, and the catch-all's Literal["pfd", "pid"]
# would 422 every plot placement (the XY body also rejects Vec3's z).
@legacy_router.put("/api/project/layout/plot/{tag}", deprecated=True)
def place_plot(
    tag: str, pos: Vec3, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> Layout:
    """Place default-project equipment on the plot plan (deprecated twin available)."""
    project = store.get()
    project.layout.plot[tag] = pos
    store.put(project)
    return project.layout


@legacy_router.put("/api/project/layout/{view}/{tag}", deprecated=True)
def place(
    view: Literal["pfd", "pid"],
    tag: str,
    pos: XY,
    store: Annotated[DbProjectStore, Depends(default_project_store)],
) -> Layout:
    """Place a default-project pfd/pid element (deprecated twin available)."""
    project = store.get()
    getattr(project.layout, view)[tag] = pos
    store.put(project)
    return project.layout


app = create_app()
