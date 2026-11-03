"""scripts/seed_trace_demo.py seeds a project the API lists, traces and audits clean."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient

from ngdesign.flowsheets import trace_demo

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_trace_demo.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_trace_demo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeded_demo_loads_traces_and_audits_clean(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/seed.db"
    trace_file = tmp_path / "trace.json"
    seed = _script()
    assert seed.main([url, "--trace-out", str(trace_file)]) == 0
    assert trace_file.stat().st_size > 0
    assert seed.main([url]) == 0  # idempotent: an existing project is left alone, not re-solved
    assert seed.main([url, "--replace"]) == 0  # same project hash: the traced solve is reused

    from ngdesign.api.app import app

    c = TestClient(app)
    rows = [p for p in c.get("/api/projects").json()["projects"] if p["name"] == trace_demo.NAME]
    assert len(rows) == 1
    pid = rows[0]["id"]

    graph = c.get(f"/api/projects/{pid}/trace", params={"unit": "K-101", "prop": "power_W"}).json()
    assert graph["meta"]["focus"]
    methods = {o["method"] for o in graph["ops"]}
    assert {"shaft_power", "isentropic_compression", "flash_ph", "tear_wegstein"} <= methods

    column = c.get(f"/api/projects/{pid}/trace", params={"stream": "S-018", "prop": "molar_flow"}).json()
    assert "column_shortcut" in {o["method"] for o in column["ops"]}

    report = c.get(f"/api/projects/{pid}/trace/audit").json()
    assert report["outputs"] > 200
    assert [f for f in report["findings"] if f["severity"] == "error"] == []
