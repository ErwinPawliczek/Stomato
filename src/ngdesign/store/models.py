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


class SchemaVersionRow(SQLModel, table=True):
    """Single-row schema-version marker (``ngdesign db upgrade`` stamps it) so
    a later Alembic migration can take over from ``create_all``."""

    __tablename__ = "schema_version"

    id: int = Field(primary_key=True)  # always 1
    version: int
    applied_at: NaiveDatetime


#: Current store schema version, bumped when a spec changes the tables above.
SCHEMA_VERSION = 1
