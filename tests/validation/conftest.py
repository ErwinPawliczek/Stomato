"""Marker registration for the P1-05 validation suite (pyproject.toml is locked)."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "validation: literature/reference property validation (spec P1-05)")
    config.addinivalue_line("markers", "slow: long-running tests")
