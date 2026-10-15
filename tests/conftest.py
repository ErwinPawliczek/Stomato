"""Shared fixtures. LOCKED."""

from __future__ import annotations

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
