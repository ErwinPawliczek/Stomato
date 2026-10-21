"""B-02 acceptance: POST /api/solve runs the current project through the real
engine (pr thermo + sequential_modular, the S-35 CLI seam), caches by project
hash, and answers 501 naming the kind when a unit plugin is missing.

The parity check compares the API response against the verified CLI slice
output (converged in 1 pass; the full CLI chain gives 5 sizer datasheets,
13 P&ID lines over 6 equipment, 0 violations).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign import pipeline, registry
from ngdesign.api.app import app
from ngdesign.cli import _solve_slice, _violations

c = TestClient(app)

#: Test-only raising unit kind, registered per test and popped afterwards.
BOOM_KIND = "p2_api_boom"
BOOM_MESSAGE = "boom: compressor surge"


class _BoomUnit:
    """A plugin bug on the API path: raises instead of returning outlets."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out",)

    def solve(self, inlets: Any, params: Any, thermo: Any) -> Any:
        raise RuntimeError(BOOM_MESSAGE)


@pytest.fixture()
def _boom_unit() -> Iterator[None]:
    registry.register("unit", BOOM_KIND)(_BoomUnit)
    yield
    registry._REGISTRY["unit"].pop(BOOM_KIND, None)  # no public unregister


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def test_solve_returns_converged_slice() -> None:
    _reset()
    r = c.post("/api/solve")
    assert r.status_code == 200
    body = r.json()
    assert body["converged"] is True
    assert body["iterations"] == 1
    project = c.get("/api/project").json()
    assert set(body["streams"]) == {s["id"] for s in project["flowsheet"]["streams"]}
    assert set(body["units"]) == {u["tag"] for u in project["flowsheet"]["units"]}


def test_solve_failed_project_answers_200_with_errors(_boom_unit: None) -> None:
    """Spec P2-02: a solve whose unit raises is a 200 carrying the partial result.

    The UI decides what to show; only invalid projects (validation errors) stay
    4xx and only missing plugins stay 501.
    """
    _reset()
    broken = {
        "name": "broken",
        "flowsheet": {
            "name": "broken",
            "units": [{"tag": "X-101", "kind": BOOM_KIND, "params": {}}],
            "streams": [
                {
                    "id": "S-001",
                    "target": {"unit": "X-101", "port": "inlet"},
                    "feed": {"T": 300.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"C1": 1.0}},
                },
                {"id": "S-002", "source": {"unit": "X-101", "port": "out"}},
            ],
        },
    }
    assert c.put("/api/project", json=broken).status_code == 200
    r = c.post("/api/solve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert body["converged"] is False
    assert body["errors"] == [
        {
            "tag": "X-101",
            "kind": BOOM_KIND,
            "error_type": "RuntimeError",
            "message": BOOM_MESSAGE,
            "stage": "solve",
            "upstream": False,
        }
    ]
    # The feed was flashed and is in the partial result; the unit has no result.
    assert set(body["streams"]) == {"S-001"}
    assert body["units"] == {}
    assert body["history"][0]["units"] == ["X-101"]
    assert body["history"][0]["converged"] is False


def test_solve_matches_cli_slice() -> None:
    """Parity: the API response equals the CLI's solve of the same project.

    History wall times are stripped before the comparison: they are telemetry,
    not results (BlockRecord equality ignores them for the same reason).
    """
    _reset()
    r = c.post("/api/solve")
    assert r.status_code == 200
    body = r.json()
    expected = _solve_slice().model_dump(mode="json")
    for record in body["history"] + expected["history"]:
        record.pop("wall_s")
    assert body == expected


def test_cli_slice_parity_numbers() -> None:
    """The verifier's CLI numbers hold on the engine seam the endpoint uses."""
    solved = _solve_slice()
    assert solved.converged is True
    assert solved.iterations == 1
    solved = pipeline.run_sizers(solved)
    assert sorted(solved.datasheets) == ["E-101", "E-102", "K-101", "T-101", "V-101"]
    pid = registry.create("pid_builder", "default").build(solved)
    rules = pipeline.rule_set(solved, k_gas=pipeline.DEFAULT_K_GAS)
    pid = pipeline.apply_rules(pid, rules)
    assert len(pid.lines) == 13
    assert len(pid.equipment) == 6
    assert _violations(pid, rules) == []


def test_solve_is_cached_by_project_hash(monkeypatch: Any) -> None:
    _reset()
    assert c.post("/api/solve").status_code == 200

    cls: Any = registry.get("solver", "sequential_modular")
    original = cls.solve
    calls: list[int] = []

    def counting(self: Any, fs: Any, thermo: Any) -> Any:
        calls.append(1)
        return original(self, fs, thermo)

    monkeypatch.setattr(cls, "solve", counting)

    # Unchanged project: served from the cache, solver not re-run.
    first = c.post("/api/solve")
    assert first.status_code == 200
    assert calls == []

    # Any project change busts the cache and re-solves.
    p = c.get("/api/project").json()
    p["layout"]["pfd"]["V-101"] = {"x": 1.0, "y": 2.0}
    assert c.put("/api/project", json=p).status_code == 200
    assert c.post("/api/solve").status_code == 200
    assert calls == [1]


def test_solve_missing_unit_kind_names_it() -> None:
    _reset()
    broken = {
        "name": "broken",
        "flowsheet": {
            "name": "broken",
            "units": [{"tag": "X-101", "kind": "no_such_unit", "params": {}}],
            "streams": [],
        },
    }
    assert c.put("/api/project", json=broken).status_code == 200
    r = c.post("/api/solve")
    assert r.status_code == 501
    assert "no_such_unit" in r.json()["detail"]


def test_solve_unknown_thermo_lists_registered() -> None:
    """An unknown thermo selection answers 501 listing every registered name."""
    _reset()
    p = c.get("/api/project").json()
    p["flowsheet"]["thermo"] = "no_such_thermo"
    assert c.put("/api/project", json=p).status_code == 200
    r = c.post("/api/solve")
    assert r.status_code == 501
    detail = r.json()["detail"]
    assert "no_such_thermo" in detail
    for name in registry.available("thermo"):
        assert name in detail


def test_solve_explicit_pr_matches_default() -> None:
    """An explicit 'pr' selection solves identically to the untouched default."""
    _reset()
    p = c.get("/api/project").json()
    p["flowsheet"]["thermo"] = "pr"
    assert c.put("/api/project", json=p).status_code == 200
    r = c.post("/api/solve")
    assert r.status_code == 200
    body = r.json()
    expected = _solve_slice().model_dump(mode="json")
    for record in body["history"] + expected["history"]:
        record.pop("wall_s")
    assert body == expected
