"""Project CRUD over the store (spec P3-01).

:class:`DbProjectStore` is bound to one project id and satisfies the agent's
``ProjectStore`` protocol (``ngdesign.agent.tools``) *structurally* — the store
never imports the agent layer, so it stays independent of it by construction.
Errors are domain types (:class:`ProjectNotFound`, :class:`ProjectExists`,
:class:`ProjectConflict`, :class:`ProjectForbidden`); the API layer maps them
to 404/409/403 exactly once, in its exception handlers.

The pydantic ``Project`` contract is stored as JSON and validated on read —
the contract never becomes columns. ``put`` bumps ``version`` and
``updated_at``; an ``expected_version`` turns the write into an optimistic
check that raises :class:`ProjectConflict` on a stale read (the HTTP PUT maps
that to 409).
"""

from __future__ import annotations

import uuid

from sqlmodel import select

from ngdesign.contracts import Project
from ngdesign.store.conversations import ConversationStore
from ngdesign.store.db import session
from ngdesign.store.models import ConversationRow, ProjectRow, utcnow

#: The legacy unscoped routes (/api/project, /api/solve, ...) are aliases bound
#: to a project with this name, created on first use (spec P3-01).
DEFAULT_PROJECT_NAME = "default"


class ProjectNotFound(Exception):
    """No project row for the requested id."""


class ProjectExists(Exception):
    """A project with the same (owner, name) already exists."""


class ProjectConflict(Exception):
    """Optimistic version check failed: the row moved since it was read."""


class ProjectForbidden(Exception):
    """The authenticated owner does not own the requested project."""


def list_projects(owner: str) -> list[ProjectRow]:
    """The owner's projects, oldest first."""
    with session() as db:
        rows = db.exec(select(ProjectRow).where(ProjectRow.owner == owner).order_by("created_at", "id")).all()
        return list(rows)


def create_project(*, name: str, owner: str, project: Project) -> ProjectRow:
    """Insert a new project row carrying ``project`` as its body."""
    row = ProjectRow(
        id=uuid.uuid4().hex,
        name=name,
        owner=owner,
        body_json=project.model_dump_json(),
        created_at=utcnow(),
        updated_at=utcnow(),
        version=1,
    )
    with session() as db:
        if (
            db.exec(select(ProjectRow).where(ProjectRow.owner == owner, ProjectRow.name == name)).first()
            is not None
        ):
            raise ProjectExists(f"a project named {name!r} already exists")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def find_project(*, name: str, owner: str) -> ProjectRow | None:
    """The owner's project with exactly this name, if any."""
    with session() as db:
        row: ProjectRow | None = db.exec(
            select(ProjectRow).where(ProjectRow.owner == owner, ProjectRow.name == name)
        ).first()
        return row


class DbProjectStore:
    """A ``ProjectStore`` over one stored project row (the API and agent's
    injected seam; spec B-08's protocol, spec P3-01's database behind it)."""

    def __init__(self, project_id: str) -> None:
        self._id = project_id

    @property
    def project_id(self) -> str:
        """The bound project id."""
        return self._id

    @property
    def conversations(self) -> ConversationStore:
        """The project's conversations (chat transcripts persist in the store)."""
        return ConversationStore(self._id)

    def row(self) -> ProjectRow:
        """The bound row; :class:`ProjectNotFound` when it is gone."""
        with session() as db:
            row: ProjectRow | None = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            return row

    def get(self) -> Project:
        """The stored contract, validated on read."""
        return Project.model_validate_json(self.row().body_json)

    def put(self, project: Project, *, expected_version: int | None = None) -> Project:
        """Store ``project``: new body JSON, ``version`` bumped, ``updated_at``
        stamped. With ``expected_version``, a row that moved since the caller
        read it raises :class:`ProjectConflict` instead."""
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            if expected_version is not None and row.version != expected_version:
                raise ProjectConflict(
                    f"project {self._id!r} was modified concurrently "
                    f"(stored version {row.version} != expected {expected_version})"
                )
            row.body_json = project.model_dump_json()
            row.version += 1
            row.updated_at = utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            return project

    def delete(self) -> None:
        """Delete the bound project and its conversations (explicit cascade)."""
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            for conversation in db.exec(
                select(ConversationRow).where(ConversationRow.project_id == self._id)
            ).all():
                db.delete(conversation)
            db.delete(row)
            db.commit()
