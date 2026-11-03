"""The project change log (docs/agentic-layer.md section 3).

Every body write is a :class:`ChangeRow` written in the same transaction as the
body, carrying both bodies: the log is the undo stack, the redo stack and the
live change feed at once. History is linear — a new edit drops every undone
edit (the redo branch) — and an undo/redo refuses with
:class:`~ngdesign.store.projects.ProjectConflict` when the stored body is not
the one the move expects, so a history move never discards an unlogged write.

The store stays independent of the agent layer: diffs are computed by the
caller from ``before``/``after``; this module only persists and moves bodies.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from ngdesign.store.models import ChangeRow, ProjectRow, utcnow

#: Changes kept per project; older rows are pruned on commit (bounded storage;
#: undo reaches back this many edits).
MAX_HISTORY = 500


class NothingToMove(LookupError):
    """Undo with no applied edit, or redo with no undone edit."""


class ChangeRecord(BaseModel):
    """One change as the store hands it out (bodies as JSON text)."""

    seq: int
    kind: str
    op: str
    actor: str
    summary: str
    args: dict[str, Any]
    state: str
    target_seq: int | None
    version: int
    created_at: datetime
    before: str
    after: str


def record(row: ChangeRow) -> ChangeRecord:
    """The public record of a row."""
    return ChangeRecord(
        seq=row.seq,
        kind=row.kind,
        op=row.op,
        actor=row.actor,
        summary=row.summary,
        args=json.loads(row.args_json),
        state=row.state,
        target_seq=row.target_seq,
        version=row.version,
        created_at=row.created_at,
        before=row.before_json,
        after=row.after_json,
    )


def _next_seq(db: Session, project_id: str) -> int:
    current = db.exec(select(func.max(ChangeRow.seq)).where(ChangeRow.project_id == project_id)).one()
    return int(current or 0) + 1


def _prune(db: Session, project_id: str) -> None:
    count = db.exec(
        select(func.count()).select_from(ChangeRow).where(ChangeRow.project_id == project_id)
    ).one()
    excess = int(count) - MAX_HISTORY
    if excess <= 0:
        return
    oldest = db.exec(
        select(ChangeRow).where(ChangeRow.project_id == project_id).order_by(col(ChangeRow.seq)).limit(excess)
    ).all()
    for row in oldest:
        db.delete(row)


def _append(
    db: Session,
    row: ProjectRow,
    *,
    kind: str,
    op: str,
    actor: str,
    summary: str,
    args: dict[str, Any],
    before_json: str,
    after_json: str,
    state: str,
    target_seq: int | None = None,
) -> ChangeRow:
    change = ChangeRow(
        id=uuid.uuid4().hex,
        project_id=row.id,
        seq=_next_seq(db, row.id),
        kind=kind,
        op=op,
        actor=actor,
        summary=summary,
        args_json=json.dumps(args, sort_keys=True, default=str),
        before_json=before_json,
        after_json=after_json,
        state=state,
        target_seq=target_seq,
        version=row.version,
        created_at=utcnow(),
    )
    db.add(change)
    return change


def write_edit(
    db: Session,
    row: ProjectRow,
    after_json: str,
    *,
    op: str,
    actor: str,
    summary: str,
    args: dict[str, Any] | None,
) -> ChangeRow:
    """Write ``after_json`` as the body of ``row`` and log the edit (caller commits).

    Drops the redo branch: every ``undone`` edit becomes ``dropped``.
    """
    before_json = row.body_json
    row.body_json = after_json
    row.version += 1
    row.updated_at = utcnow()
    db.add(row)
    for undone in db.exec(
        select(ChangeRow).where(ChangeRow.project_id == row.id, ChangeRow.state == "undone")
    ).all():
        undone.state = "dropped"
        db.add(undone)
    change = _append(
        db,
        row,
        kind="edit",
        op=op,
        actor=actor,
        summary=summary,
        args=args or {},
        before_json=before_json,
        after_json=after_json,
        state="applied",
    )
    _prune(db, row.id)
    return change


def move(db: Session, row: ProjectRow, *, direction: str, actor: str) -> ChangeRow:
    """Undo (``direction="undo"``) or redo one edit of ``row`` (caller commits).

    Raises :class:`NothingToMove` with nothing to move, and ``ValueError`` when
    the stored body is not the one the move starts from (the caller maps it to
    its conflict type).
    """
    if direction == "undo":
        target = db.exec(
            select(ChangeRow)
            .where(ChangeRow.project_id == row.id, ChangeRow.kind == "edit", ChangeRow.state == "applied")
            .order_by(col(ChangeRow.seq).desc())
        ).first()
        if target is None:
            raise NothingToMove("nothing to undo: no applied change in this project's history")
        expected, restored, new_state = target.after_json, target.before_json, "undone"
    elif direction == "redo":
        target = db.exec(
            select(ChangeRow)
            .where(ChangeRow.project_id == row.id, ChangeRow.kind == "edit", ChangeRow.state == "undone")
            .order_by(col(ChangeRow.seq))
        ).first()
        if target is None:
            raise NothingToMove("nothing to redo: no undone change (a new edit clears the redo history)")
        expected, restored, new_state = target.before_json, target.after_json, "applied"
    else:
        raise ValueError(f"direction must be 'undo' or 'redo', got {direction!r}")
    if row.body_json != expected:
        raise ValueError(
            f"cannot {direction} change #{target.seq} ({target.summary}): the project was changed "
            "outside the recorded history since"
        )
    before_json = row.body_json
    row.body_json = restored
    row.version += 1
    row.updated_at = utcnow()
    db.add(row)
    target.state = new_state
    db.add(target)
    verb = "Undo" if direction == "undo" else "Redo"
    return _append(
        db,
        row,
        kind=direction,
        op=direction,
        actor=actor,
        summary=f"{verb}: {target.summary}",
        args={"target_seq": target.seq},
        before_json=before_json,
        after_json=restored,
        state="record",
        target_seq=target.seq,
    )


def list_changes(db: Session, project_id: str, *, after: int = 0, limit: int = 100) -> list[ChangeRow]:
    """Changes with ``seq > after``, oldest first, at most ``limit``."""
    rows = db.exec(
        select(ChangeRow)
        .where(ChangeRow.project_id == project_id, ChangeRow.seq > after)
        .order_by(col(ChangeRow.seq))
        .limit(limit)
    ).all()
    return list(rows)


def delete_changes(db: Session, project_id: str) -> None:
    """Every change of a project (explicit cascade on project delete)."""
    for row in db.exec(select(ChangeRow).where(ChangeRow.project_id == project_id)).all():
        db.delete(row)


__all__ = [
    "MAX_HISTORY",
    "ChangeRecord",
    "NothingToMove",
    "delete_changes",
    "list_changes",
    "move",
    "record",
    "write_edit",
]
