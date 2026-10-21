"""Agent conversation persistence (spec P3-01).

Conversations live in ``ConversationRow`` keyed by the client round-tripped
``conversation_id``, scoped to one project — the in-memory dict from B-08 is
gone, so a restart keeps the transcripts. The message history is the Anthropic
API shape (dicts with ``role``/``content``), serialized as JSON exactly as the
transcript endpoint replays it.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select

from ngdesign.store.db import session
from ngdesign.store.models import ConversationRow, utcnow

Message = dict[str, Any]


class ConversationStore:
    """The conversations of one project."""

    def __init__(self, project_id: str) -> None:
        self._project_id = project_id

    def list_ids(self) -> list[str]:
        """Every conversation id of this project, sorted."""
        with session() as db:
            rows = db.exec(
                select(ConversationRow).where(ConversationRow.project_id == self._project_id)
            ).all()
            return sorted(row.id for row in rows)

    def load(self, conversation_id: str) -> list[Message] | None:
        """The stored history, or None when the id is unknown here."""
        with session() as db:
            row = db.get(ConversationRow, conversation_id)
            if row is None or row.project_id != self._project_id:
                return None
            messages: list[Message] = json.loads(row.messages_json)
            return messages

    def save(self, conversation_id: str, messages: list[Message]) -> None:
        """Upsert one conversation's history."""
        with session() as db:
            row = db.get(ConversationRow, conversation_id)
            if row is None:
                row = ConversationRow(
                    id=conversation_id, project_id=self._project_id, messages_json="[]", updated_at=utcnow()
                )
            row.messages_json = json.dumps(messages)
            row.updated_at = utcnow()
            db.add(row)
            db.commit()

    def delete(self, conversation_id: str) -> bool:
        """Forget one conversation; True when it existed in this project."""
        with session() as db:
            row = db.get(ConversationRow, conversation_id)
            if row is None or row.project_id != self._project_id:
                return False
            db.delete(row)
            db.commit()
            return True


def delete_all_conversations() -> None:
    """Forget every conversation of every project (test isolation seam)."""
    with session() as db:
        for row in db.exec(select(ConversationRow)).all():
            db.delete(row)
        db.commit()
