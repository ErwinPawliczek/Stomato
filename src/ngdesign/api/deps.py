"""FastAPI dependencies handing route handlers a :class:`DbProjectStore`.

``project_store`` resolves a path project id (404 unknown, 403 foreign owner);
``default_project_store`` binds the legacy unscoped routes to the project named
``default``, created on first use from the sample slice — the current frontend
keeps working unchanged (spec P3-01).
"""

from __future__ import annotations

from fastapi import Depends

from ngdesign.api.auth import current_owner
from ngdesign.contracts import Project
from ngdesign.store import (
    DEFAULT_PROJECT_NAME,
    DbProjectStore,
    ProjectExists,
    ProjectForbidden,
    ProjectNotFound,
    create_project,
    find_project,
)


def slice_project() -> Project:
    """The sample slice, verbatim (the legacy GET /api/project pins its name)."""
    from ngdesign.flowsheets import slice as slice_fs

    return Project(name="slice", flowsheet=slice_fs.build())


def project_store(project_id: str, owner: str = Depends(current_owner)) -> DbProjectStore:
    """The store bound to the path project; 404 unknown, 403 foreign owner."""
    store = DbProjectStore(project_id)
    try:
        row = store.row()
    except ProjectNotFound:
        raise ProjectNotFound(f"unknown project {project_id!r}") from None
    if row.owner != owner:
        raise ProjectForbidden(f"project {project_id!r} belongs to another owner")
    return store


def default_project_store(owner: str = Depends(current_owner)) -> DbProjectStore:
    """The store bound to the owner's ``default`` project, created on first use."""
    row = find_project(name=DEFAULT_PROJECT_NAME, owner=owner)
    if row is None:
        try:
            row = create_project(name=DEFAULT_PROJECT_NAME, owner=owner, project=slice_project())
        except ProjectExists:
            # Two first requests raced on the unique (owner, name): the other one won.
            row = find_project(name=DEFAULT_PROJECT_NAME, owner=owner)
            assert row is not None
    return DbProjectStore(row.id)
