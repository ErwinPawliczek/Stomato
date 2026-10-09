"""Shared fixtures. LOCKED."""

from __future__ import annotations

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
    return registry.create("thermo", "pr" if "pr" in names else names[0])


def flash_feed(thermo: Thermo, feed: dict | FeedSpec) -> StreamState:
    f = feed if isinstance(feed, FeedSpec) else FeedSpec(**feed)
    return thermo.flash_pt(f.composition, f.T, f.P, f.molar_flow)
