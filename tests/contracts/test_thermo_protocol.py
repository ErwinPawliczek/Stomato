"""Every registered thermo package satisfies the contract-v2 Thermo protocol (P1-01)."""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.thermo import catalogue


@pytest.mark.parametrize("name", registry.available("thermo"))
def test_registered_thermo_satisfies_protocol(name: str) -> None:
    try:
        instance = registry.create("thermo", name)
    except NotImplementedError as exc:
        # Experimental rows may refuse to build until their engine or cited
        # parameters exist (the saft refusal rows); the refusal is only legitimate
        # when the row's own l0 coverage declares it.
        rows = dict(catalogue.load_catalogue())
        row = rows.get(name)
        declared = row is not None and bool(row.l0_excluded)
        if not declared:
            raise
        pytest.skip(f"{name} refuses to build: {exc}")
    assert isinstance(instance, Thermo)
