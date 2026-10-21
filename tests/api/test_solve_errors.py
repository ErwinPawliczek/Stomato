"""C-4 acceptance: the solve seam's failure surface.

- A project whose unit kind has no registered plugin answers 501 naming the kind on
  every route that reaches the engine (solve, pfd.svg, pid.svg; the route/plot.svg
  pair is pinned in tests/api/test_plot.py).
- A failed 501 never poisons the result cache.
- Non-convergence is a *result*, not an error: the solver never raises for
  non-convergence (sequential_modular contract, spec S-30), so POST /api/solve
  answers 200 with converged=false at the iteration cap, and the views still render.
- A stream naming a port the unit plugin does not declare (ports are only known to
  the plugins at solve time) is also a *result*, not an error, since spec P2-02:
  the solve answers 200 with a stage="ports" UnitError naming the port in the
  partial SolvedFlowsheet, never an unhandled 500.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import ngdesign.solver.sequential_modular as sequential_modular
from ngdesign.api import routes_solve
from ngdesign.api.app import app

c = TestClient(app)


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _put_unknown_kind_project() -> None:
    """Replace the slice with a schema-valid project whose unit has no plugin."""
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


def test_unknown_unit_kind_names_it_on_every_engine_route() -> None:
    _put_unknown_kind_project()
    for method, path in (
        ("post", "/api/solve"),
        ("get", "/api/views/pfd.svg"),
        ("get", "/api/views/pid.svg"),
    ):
        r = getattr(c, method)(path)
        assert r.status_code == 501, f"{method} {path}: {r.text}"
        assert "no_such_unit" in r.json()["detail"]


def test_failed_solve_does_not_poison_the_cache() -> None:
    _put_unknown_kind_project()
    assert c.post("/api/solve").status_code == 501
    _reset()  # identical PUT-time shape to any other slice project: hash must re-solve
    r = c.post("/api/solve")
    assert r.status_code == 200
    assert r.json()["converged"] is True


def test_non_convergence_is_a_result_not_an_error(monkeypatch: Any) -> None:
    """Force the tear loop past its budget: 200 + converged=false at the cap.

    The sample slice is acyclic (every topological block is a singleton, no
    tears), so the non-convergence path never runs on it. Force the loop the
    way a recycle would: designate a real stream as the tear (the seam
    _pick_tears fills for actual cycles) and make the tear vector never
    converge. The solver then iterates the real Wegstein loop to its cap and
    reports failure as data, never an exception.
    """
    monkeypatch.setattr(routes_solve, "_cache", {})  # isolate from parallel tests in this worker
    _reset()
    project = c.get("/api/project").json()

    # A full 100-pass tear loop re-solves the slice ~100x (~60 s): shrink the cap
    # to keep the surface test fast; the cap value itself is what we assert on.
    monkeypatch.setattr(sequential_modular, "MAX_ITERATIONS", 3)

    def forced_tear(fs: Any, block: Any) -> set[str]:
        return {fs.streams[0].id}

    monkeypatch.setattr(sequential_modular, "_pick_tears", forced_tear)
    monkeypatch.setattr(sequential_modular, "_converged", lambda x, y: False)
    assert c.put("/api/project", json=project).status_code == 200

    r = c.post("/api/solve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["converged"] is False
    assert body["iterations"] == 3
    # The failed solve is a cached result like any other: served identically.
    assert c.post("/api/solve").json() == body
    # Views render the non-converged solve (they gate on nothing else).
    assert c.get("/api/views/pfd.svg").status_code == 200


def test_unknown_port_is_a_recorded_error_not_a_crash(monkeypatch: Any) -> None:
    """Schema-valid PUT, mistyped port: 200 with a stage="ports" error (P2-02)."""
    monkeypatch.setattr(routes_solve, "_cache", {})
    _reset()
    project = c.get("/api/project").json()
    stream = next(s for s in project["flowsheet"]["streams"] if s["source"] is not None)
    stream["source"]["port"] = "no_such_port"
    assert c.put("/api/project", json=project).status_code == 200

    r = c.post("/api/solve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    ports_errors = [e for e in body["errors"] if e["stage"] == "ports"]
    assert ports_errors
    assert all("no_such_port" in e["message"] for e in ports_errors)
    assert all(e["upstream"] is False for e in ports_errors)
