"""Every registered thermo package satisfies the contract-v2 Thermo protocol (P1-01)."""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo


@pytest.mark.parametrize("name", registry.available("thermo"))
def test_registered_thermo_satisfies_protocol(name: str) -> None:
    assert isinstance(registry.create("thermo", name), Thermo)
