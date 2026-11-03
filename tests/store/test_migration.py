"""Store schema v1 -> v2 migration: a database written by the P3-01 schema
keeps every project (the legacy ``default`` one included) and gains the
multi-project columns in place."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ngdesign.api.app import create_app
from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.store import init_db, reset_engine, session
from ngdesign.store.models import SCHEMA_VERSION, SchemaVersionRow

# The P3-01 (schema v1) DDL as SQLModel emitted it for SQLite.
_V1_DDL = """
CREATE TABLE projects (
    id VARCHAR NOT NULL, name VARCHAR NOT NULL, owner VARCHAR NOT NULL, body_json VARCHAR NOT NULL,
    created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, version INTEGER NOT NULL,
    PRIMARY KEY (id), CONSTRAINT uq_projects_owner_name UNIQUE (owner, name)
);
CREATE INDEX ix_projects_name ON projects (name);
CREATE INDEX ix_projects_owner ON projects (owner);
CREATE TABLE conversations (
    id VARCHAR NOT NULL, project_id VARCHAR NOT NULL, messages_json VARCHAR NOT NULL,
    updated_at DATETIME NOT NULL, PRIMARY KEY (id), FOREIGN KEY(project_id) REFERENCES projects (id)
);
CREATE TABLE schema_version (
    id INTEGER NOT NULL, version INTEGER NOT NULL, applied_at DATETIME NOT NULL, PRIMARY KEY (id)
);
"""


def _v1_database(path: Path) -> str:
    body = Project(name="slice", flowsheet=slice_fs.build()).model_dump_json()
    with sqlite3.connect(path) as db:
        db.executescript(_V1_DDL)
        db.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p1", "default", "local", body, "2026-01-01 00:00:00", "2026-01-02 00:00:00", 7),
        )
        db.execute("INSERT INTO conversations VALUES ('c1', 'p1', '[]', '2026-01-02 00:00:00')")
        db.execute("INSERT INTO schema_version VALUES (1, 1, '2026-01-01 00:00:00')")
    return body


@pytest.fixture()
def v1_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    path = tmp_path / "v1.db"
    body = _v1_database(path)
    monkeypatch.setenv("STOMATO_DATABASE_URL", f"sqlite:///{path}")
    reset_engine()
    return path, body


def test_v1_database_migrates_in_place_and_keeps_the_project(v1_db: tuple[Path, str]) -> None:
    path, body = v1_db
    init_db()
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
        rows = db.execute(
            "SELECT id, name, owner, body_json, version, template, opened_at FROM projects"
        ).fetchall()
        conversations = db.execute("SELECT id, project_id FROM conversations").fetchall()
    assert {"template", "opened_at"} <= columns
    assert rows == [("p1", "default", "local", body, 7, None, None)]
    assert conversations == [("c1", "p1")]
    with session() as db:
        stamp = db.get(SchemaVersionRow, 1)
        assert stamp is not None and stamp.version == SCHEMA_VERSION == 2


def test_migration_is_idempotent(v1_db: tuple[Path, str]) -> None:
    path, _ = v1_db
    init_db()
    reset_engine()
    init_db()  # second start over the migrated file: nothing to add, no error
    with sqlite3.connect(path) as db:
        names = [row[1] for row in db.execute("PRAGMA table_info(projects)")]
    assert names.count("template") == 1 and names.count("opened_at") == 1


def test_migrated_project_is_served_listed_and_renamable(v1_db: tuple[Path, str]) -> None:
    client = TestClient(create_app())
    listing = client.get("/api/projects").json()["projects"]
    assert [(p["id"], p["name"], p["template"], p["opened_at"]) for p in listing] == [
        ("p1", "default", None, None)
    ]
    # The legacy alias still resolves the existing project, not a fresh one.
    assert client.get("/api/project").json()["name"] == "slice"
    assert len(client.get("/api/projects").json()["projects"]) == 1
    assert client.post("/api/projects/p1/open").json()["opened_at"] is not None
    renamed = client.patch("/api/projects/p1", json={"name": "Dehydration"}).json()
    assert renamed["name"] == "Dehydration" and renamed["version"] == 8
