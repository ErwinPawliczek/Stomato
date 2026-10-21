"""The project store (spec P3-01): SQLModel tables, engine/sessions, project
CRUD and conversation persistence.

Layer placement: directly below ``ngdesign.api`` and above ``ngdesign.agent`` —
the API may import the store, the agent may not (the agent keeps its
``ProjectStore`` protocol from B-08; :class:`DbProjectStore` satisfies it
structurally without importing it). The store itself imports only the
contracts and SQLModel — no agent, no API, no flowsheets.
"""

from ngdesign.store.conversations import ConversationStore, delete_all_conversations
from ngdesign.store.db import database_url, database_url_log_safe, init_db, reset_engine, session
from ngdesign.store.models import ConversationRow, ProjectRow, SchemaVersionRow, SolveRow
from ngdesign.store.projects import (
    DEFAULT_PROJECT_NAME,
    DbProjectStore,
    ProjectConflict,
    ProjectExists,
    ProjectForbidden,
    ProjectNotFound,
    create_project,
    find_project,
    list_projects,
)

__all__ = [
    "DEFAULT_PROJECT_NAME",
    "ConversationRow",
    "ConversationStore",
    "DbProjectStore",
    "ProjectConflict",
    "ProjectExists",
    "ProjectForbidden",
    "ProjectNotFound",
    "ProjectRow",
    "SchemaVersionRow",
    "SolveRow",
    "create_project",
    "database_url",
    "database_url_log_safe",
    "delete_all_conversations",
    "find_project",
    "init_db",
    "list_projects",
    "reset_engine",
    "session",
]
