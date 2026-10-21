"""Store test isolation (spec P3-01): same contract as tests/api/conftest.py —
one SQLite file per test, engines and auth caches dropped around it."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ngdesign.api import auth
from ngdesign.store import reset_engine


@pytest.fixture(autouse=True)
def _store_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STOMATO_DATABASE_URL", f"sqlite:///{tmp_path}/store.db")
    monkeypatch.delenv("STOMATO_API_TOKENS", raising=False)
    auth.reset_auth_cache()
    reset_engine()
    yield
    auth.reset_auth_cache()
    reset_engine()
