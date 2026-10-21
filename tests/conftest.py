"""Shared fixtures. LOCKED."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, StreamState
from ngdesign.contracts.plugins import Thermo


@pytest.fixture(scope="session")
def thermo() -> Thermo:
    """The registered Peng-Robinson package. Skips if none is registered yet."""
    names = registry.available("thermo")
    if not names:
        pytest.skip("no thermo plugin registered yet (spec S-01)")
    impl: Thermo = registry.create("thermo", "pr" if "pr" in names else names[0])
    return impl


def flash_feed(thermo: Thermo, feed: dict[str, Any] | FeedSpec) -> StreamState:
    f = feed if isinstance(feed, FeedSpec) else FeedSpec(**feed)
    return thermo.flash_pt(f.composition, f.T, f.P, f.molar_flow)


@pytest.fixture(autouse=True)
def _store_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test gets its own SQLite file, open auth and a dropped engine/auth
    cache (spec P3-01), so no test writes ./stomato.db or sees another's rows."""
    from ngdesign.api import auth
    from ngdesign.store import reset_engine

    monkeypatch.setenv("STOMATO_DATABASE_URL", f"sqlite:///{tmp_path}/store.db")
    monkeypatch.delenv("STOMATO_API_TOKENS", raising=False)
    auth.reset_auth_cache()
    reset_engine()
    yield
    auth.reset_auth_cache()
    reset_engine()
