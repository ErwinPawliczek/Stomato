"""docs/coverage-gaps.md is generated: it may not drift from the catalogues."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "coverage_audit.py"


def test_the_gap_list_is_current() -> None:
    spec = importlib.util.spec_from_file_location("coverage_audit", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TARGET.read_text() == module.build()
