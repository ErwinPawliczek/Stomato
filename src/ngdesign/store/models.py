"""SQLModel tables for the project store (spec P3-01).

One row per durable concept: ``ProjectRow`` carries the pydantic ``Project``
contract as JSON (``model_dump_json`` out, validated ``model_validate_json`` in
— the contract never becomes columns), ``ConversationRow`` keeps the agent's
Anthropic-shaped message history, and ``SolveRow`` is the schema P3-02's job
model will hang solves on (defined here so the schema lands once; this spec
does not write to it). ``SchemaVersionRow`` records the schema version so a
later Alembic migration can take over (``ngdesign db init|upgrade``).

Datetimes are naive UTC (dialect-proof across SQLite and Postgres).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import NaiveDatetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Naive UTC now — stored identically on SQLite and Postgres."""
    return datetime.now(UTC).replace(tzinfo=None)


class ProjectRow(SQLModel, table=True):
    """One stored project. ``name`` is unique per owner (the legacy aliases
    resolve their project by the name ``default``)."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner", "name", name="uq_projects_owner_name"),)

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    owner: str = Field(index=True)
    body_json: str
    created_at: NaiveDatetime
    updated_at: NaiveDatetime
    version: int = 1
    # Schema v2 (multi-project): the catalogue template the project started
    # from (None: imported, copied, or created before v2), and when it was last
    # opened (None: never opened since v2) for the Home view's recency order.
    template: str | None = None
    opened_at: NaiveDatetime | None = None


class ConversationRow(SQLModel, table=True):
    """One agent conversation: the message history in Anthropic API shape."""

    __tablename__ = "conversations"

    id: str = Field(primary_key=True)  # the conversation_id the client round-trips
    project_id: str = Field(foreign_key="projects.id", index=True)
    messages_json: str
    updated_at: NaiveDatetime


class SolveRow(SQLModel, table=True):
    """One solve result, keyed by project hash (schema for spec P3-02's job
    model; P3-01 defines the table and writes nothing to it)."""

    __tablename__ = "solves"

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    project_hash: str = Field(index=True)
    status: str
    result_json: str
    created_at: NaiveDatetime


class ChangeRow(SQLModel, table=True):
    """One recorded project change (docs/agentic-layer.md section 3).

    Every body write goes through :meth:`DbProjectStore.commit` and lands here
    with the full before/after bodies, so any edit (REST, UI, in-app agent,
    MCP) is undoable and the change feed can show who changed what. ``kind``:
    ``edit`` (a body write), ``undo``/``redo`` (history moves, which point at the
    edit they moved through ``target_seq``). ``state`` applies to edits:
    ``applied``, ``undone`` (redo-able) or ``dropped`` (a later edit discarded
    the redo branch); undo/redo rows are ``record``.
    """

    __tablename__ = "changes"
    __table_args__ = (UniqueConstraint("project_id", "seq", name="uq_changes_project_seq"),)

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    seq: int = Field(index=True)
    kind: str  # edit | undo | redo
    op: str  # the operation name, e.g. "place_unit", "put", "set_cell"
    actor: str  # api | ui | agent:<conversation> | mcp[:client]
    summary: str
    args_json: str
    before_json: str
    after_json: str
    state: str  # applied | undone | dropped | record
    target_seq: int | None = None
    version: int  # the project version after this change
    created_at: NaiveDatetime


class SchemaVersionRow(SQLModel, table=True):
    """Single-row schema-version marker (``ngdesign db upgrade`` stamps it) so
    a later Alembic migration can take over from ``create_all``."""

    __tablename__ = "schema_version"

    id: int = Field(primary_key=True)  # always 1
    version: int
    applied_at: NaiveDatetime


#: Current store schema version, bumped when a spec changes the tables above.
#: v1: P3-01 tables. v2: ``projects.template`` and ``projects.opened_at``
#: (nullable; ``db.init_db`` adds them to a v1 database in place). v3: the
#: ``changes`` table (agentic layer: undoable change log; ``create_all`` adds it).
SCHEMA_VERSION = 3
