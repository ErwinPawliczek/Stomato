"""B-02 acceptance: POST /api/solve runs the current project through the real
engine (pr thermo + sequential_modular, the S-35 CLI seam), caches by project
hash, and answers 501 naming the kind when a unit plugin is missing.

The parity check compares the API response against the verified CLI slice
output (converged in 1 pass; the full CLI chain gives 5 sizer datasheets,
13 P&ID lines over 6 equipment, 0 violations).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api.app import app
from ngdesign.cli import _apply_rules, _rule_set, _run_sizers, _solve_slice, _violations

c = TestClient(app)


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


def test_solve_matches_cli_slice() -> None:
    """Parity: the API response equals the CLI's solve of the same project."""
    _reset()
    r = c.post("/api/solve")
    assert r.status_code == 200
    assert r.json() == _solve_slice().model_dump(mode="json")


def test_cli_slice_parity_numbers() -> None:
    """The verifier's CLI numbers hold on the engine seam the endpoint uses."""
    solved = _solve_slice()
    assert solved.converged is True
    assert solved.iterations == 1
    solved = _run_sizers(solved)
    assert sorted(solved.datasheets) == ["E-101", "E-102", "K-101", "T-101", "V-101"]
    pid = registry.create("pid_builder", "default").build(solved)
    rules = _rule_set(solved)
    pid = _apply_rules(pid, rules)
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
    assert r.json() == _solve_slice().model_dump(mode="json")
