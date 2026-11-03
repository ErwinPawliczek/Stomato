"""Database engine, sessions and in-place schema migration (spec P3-01).

The engine is a process-global built lazily from ``STOMATO_DATABASE_URL``
(default ``sqlite:///./stomato.db``; Postgres via ``postgresql+psycopg://`` —
the driver is the ``postgres`` optional extra). Laziness is deliberate: the
first request on a fresh database creates the schema, so a bare
``TestClient(app)`` (no lifespan) works exactly like a deployed uvicorn that
ran ``init_db()`` at startup.

``reset_engine()`` is the restart seam: dropping the cached engine (and the
init flag) makes a fresh ``create_app()`` read the same file through a new
engine — the store has no in-memory project state to carry over.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlmodel import Session, SQLModel, create_engine, select

from ngdesign.store.models import SCHEMA_VERSION, ProjectRow, SchemaVersionRow, utcnow

logger = logging.getLogger("ngdesign.store")

DATABASE_URL_ENV = "STOMATO_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///./stomato.db"

_engine: Engine | None = None
_initialized = False
_lock = threading.Lock()


def database_url() -> str:
    """The configured database URL (env only; never a hardcoded host)."""
    return os.environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


def database_url_log_safe() -> str:
    """The database URL with any password masked — the only form ever logged."""
    return make_url(database_url()).render_as_string(hide_password=True)


def get_engine() -> Engine:
    """The process-global engine, built on first use."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = _build_engine(database_url())
    return _engine


def _build_engine(url: str) -> Engine:
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a threadpool: a file SQLite database
        # is shared across threads by design here.
        connect_args["check_same_thread"] = False
    if connect_args:
        kwargs["connect_args"] = connect_args
    return create_engine(url, **kwargs)


def reset_engine() -> None:
    """Dispose the cached engine and forget the init flag (restart/test seam)."""
    global _engine, _initialized
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _initialized = False


#: Columns schema v2 added to ``projects`` (all nullable, so existing rows
#: stay valid with NULL): the in-place v1 -> v2 migration adds exactly these.
_V2_PROJECT_COLUMNS = ("template", "opened_at")


def _migrate(conn: Connection) -> list[str]:
    """Bring an older database's tables up to the current models in place.

    ``create_all`` creates missing tables but never alters existing ones, so a
    v1 ``projects`` table lacks the v2 columns. Each missing one is added with
    ``ALTER TABLE ... ADD COLUMN`` (its type compiled for the connected
    dialect); rows are untouched, so every existing project — the legacy
    ``default`` one included — survives. Idempotent: present columns are
    skipped. Returns the columns added.
    """
    present = {col["name"] for col in inspect(conn).get_columns(ProjectRow.__tablename__)}
    table = ProjectRow.__table__  # type: ignore[attr-defined]
    added: list[str] = []
    for name in _V2_PROJECT_COLUMNS:
        if name in present:
            continue
        col_type = table.c[name].type.compile(dialect=conn.dialect)
        conn.execute(text(f"ALTER TABLE {ProjectRow.__tablename__} ADD COLUMN {name} {col_type}"))
        added.append(name)
    return added


def init_db() -> None:
    """Create every table, migrate an older schema in place, and stamp the
    schema version (idempotent)."""
    engine = get_engine()
    with _lock:
        SQLModel.metadata.create_all(engine)
        with engine.begin() as conn:
            added = _migrate(conn)
        if added:
            logger.info("migrated store schema: added projects.%s", ", projects.".join(added))
        with Session(engine) as session:
            row = session.exec(select(SchemaVersionRow).where(SchemaVersionRow.id == 1)).first()
            if row is None:
                session.add(SchemaVersionRow(id=1, version=SCHEMA_VERSION, applied_at=utcnow()))
            elif row.version < SCHEMA_VERSION:
                row.version = SCHEMA_VERSION
                row.applied_at = utcnow()
                session.add(row)
            elif row.version > SCHEMA_VERSION:
                logger.warning(
                    "database schema version %s is newer than this code's schema version %s",
                    row.version,
                    SCHEMA_VERSION,
                )
            session.commit()
        global _initialized
        _initialized = True


def _ensure_initialized() -> None:
    """Lazy schema creation so a fresh database serves its first request."""
    if not _initialized:
        init_db()


@contextmanager
def session() -> Iterator[Session]:
    """One store transaction: commit on success, rollback on error, always close.

    ``expire_on_commit=False`` keeps rows usable after the session closes —
    the store hands detached ``ProjectRow`` objects to the API layer, and a
    trailing commit would otherwise re-expire every attribute and turn the
    next read into a ``DetachedInstanceError``.
    """
    _ensure_initialized()
    with Session(get_engine(), expire_on_commit=False) as db:
        yield db
        db.commit()
