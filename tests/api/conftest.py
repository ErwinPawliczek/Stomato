"""API test isolation for the store (spec P3-01).

Every test gets its own SQLite file (fresh schema, lazy init), open auth, and
a dropped engine/auth cache so nothing leaks between tests. Runs before the
per-module fixtures (conftest fixtures instantiate first), so
``routes_agent.reset_sessions()`` in test_agent_route.py sees a ready store.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ngdesign.api import auth
from ngdesign.store import reset_engine


@pytest.fixture(autouse=True)
def _store_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STOMATO_DATABASE_URL", f"sqlite:///{tmp_path}/api-store.db")
    monkeypatch.delenv("STOMATO_API_TOKENS", raising=False)
    auth.reset_auth_cache()
    reset_engine()
    yield
    auth.reset_auth_cache()
    reset_engine()
