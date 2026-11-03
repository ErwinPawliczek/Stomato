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
from typing import Any

from sqlmodel import select

from ngdesign.contracts import Project
from ngdesign.store import changes
from ngdesign.store.changes import ChangeRecord
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


def create_project(*, name: str, owner: str, project: Project, template: str | None = None) -> ProjectRow:
    """Insert a new project row carrying ``project`` as its body; ``template``
    records the catalogue template it started from (None: imported/copied)."""
    row = ProjectRow(
        id=uuid.uuid4().hex,
        name=name,
        owner=owner,
        body_json=project.model_dump_json(),
        created_at=utcnow(),
        updated_at=utcnow(),
        version=1,
        template=template,
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

    def put(self, project: Project, *, expected_version: int | None = None, actor: str = "api") -> Project:
        """Store ``project``: new body JSON, ``version`` bumped, ``updated_at``
        stamped, and the write logged as an undoable ``put`` change. With
        ``expected_version``, a row that moved since the caller read it raises
        :class:`ProjectConflict` instead."""
        self.commit(
            project, op="put", actor=actor, summary="Replaced the project", expected_version=expected_version
        )
        return project

    def commit(
        self,
        project: Project,
        *,
        op: str,
        actor: str,
        summary: str,
        args: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> ChangeRecord | None:
        """Store ``project`` and log the write as one change, in one transaction
        (docs/agentic-layer.md section 3). Returns the change, or ``None`` when
        the body is unchanged — a no-op write still bumps ``version`` (the
        P3-01 contract) but records nothing to undo."""
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            if expected_version is not None and row.version != expected_version:
                raise ProjectConflict(
                    f"project {self._id!r} was modified concurrently "
                    f"(stored version {row.version} != expected {expected_version})"
                )
            body = project.model_dump_json()
            if body == row.body_json:
                row.version += 1
                row.updated_at = utcnow()
                db.add(row)
                db.commit()
                return None
            change = changes.write_edit(db, row, body, op=op, actor=actor, summary=summary, args=args)
            db.commit()
            db.refresh(change)
            return changes.record(change)

    def undo(self, *, actor: str) -> ChangeRecord:
        """Revert the latest applied change; :class:`NothingToMove` when there is
        none, :class:`ProjectConflict` when the body moved outside the log."""
        return self._move("undo", actor)

    def redo(self, *, actor: str) -> ChangeRecord:
        """Re-apply the most recently undone change (see :meth:`undo`)."""
        return self._move("redo", actor)

    def _move(self, direction: str, actor: str) -> ChangeRecord:
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            try:
                change = changes.move(db, row, direction=direction, actor=actor)
            except ValueError as exc:
                raise ProjectConflict(str(exc)) from exc
            db.commit()
            db.refresh(change)
            return changes.record(change)

    def changes(self, *, after: int = 0, limit: int = 100) -> list[ChangeRecord]:
        """The change log with ``seq > after``, oldest first."""
        with session() as db:
            return [changes.record(r) for r in changes.list_changes(db, self._id, after=after, limit=limit)]

    def rename(self, name: str) -> ProjectRow:
        """Rename the project: the row name (unique per owner) and the body's
        ``Project.name`` move together, so the Home list, the drawings' title
        blocks and an exported file agree. Bumps ``version`` like ``put``.
        :class:`ProjectExists` when the owner has another project of that name."""
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            clash = db.exec(
                select(ProjectRow).where(
                    ProjectRow.owner == row.owner, ProjectRow.name == name, ProjectRow.id != self._id
                )
            ).first()
            if clash is not None:
                raise ProjectExists(f"a project named {name!r} already exists")
            body = Project.model_validate_json(row.body_json)
            old_name = row.name
            row.name = name
            changes.write_edit(
                db,
                row,
                body.model_copy(update={"name": name}).model_dump_json(),
                op="rename",
                actor="api",
                summary=f"Renamed the project {old_name!r} -> {name!r}",
                args={"name": name},
            )
            db.commit()
            db.refresh(row)
            return row

    def mark_opened(self) -> ProjectRow:
        """Stamp ``opened_at`` (the Home view's recency order). Not an edit:
        ``version`` and ``updated_at`` stay put."""
        with session() as db:
            row = db.get(ProjectRow, self._id)
            if row is None:
                raise ProjectNotFound(f"unknown project {self._id!r}")
            row.opened_at = utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

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
            changes.delete_changes(db, self._id)
            db.delete(row)
            db.commit()
