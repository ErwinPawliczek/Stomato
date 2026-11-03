"""The response fields the frontend reads (frontend/src/api/client.ts and its
views), for the calls no other tests/api module pins field by field, and the
status the views branch on when a project cannot be drawn.

Already covered elsewhere and not repeated here: GET /api/meta (test_meta,
test_app), GET/PUT /api/project and the pfd placement (test_app), the pfd/pid/
plot SVG data-tag structure and placements (test_views, test_pid_view,
test_plot), POST /api/route (test_plot), the 501 paths (test_solve_errors) and
the agent SSE events (test_agent_route).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def _with_unwired_unit() -> dict[str, Any]:
    """The default project plus a unit as the add-unit palette inserts it:
    a fresh tag, the kind's default params, no streams wired yet."""
    project: dict[str, Any] = c.get("/api/project").json()
    project["flowsheet"]["units"].append(
        {"tag": "E-901", "kind": "cooler", "params": {"T_out": 313.15, "dP": 35000.0}}
    )
    assert c.put("/api/project", json=project).status_code == 200
    return project


def test_solve_carries_every_field_results_view_reads() -> None:
    """ResultsView: converged, iterations, streams[id].{T,P,molar_flow,
    vapor_fraction} and units[tag].{duty_W,power_W,info{str: number}}."""
    r = c.post("/api/solve")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["converged"], bool)
    assert isinstance(body["iterations"], int)
    assert body["streams"]
    for st in body["streams"].values():
        for key in ("T", "P", "molar_flow", "vapor_fraction"):
            assert isinstance(st[key], int | float), key
    tags = {u["tag"] for u in c.get("/api/project").json()["flowsheet"]["units"]}
    assert set(body["units"]) == tags
    for ur in body["units"].values():
        assert isinstance(ur["duty_W"], int | float)
        assert isinstance(ur["power_W"], int | float)
        assert all(isinstance(k, str) and isinstance(v, int | float) for k, v in ur["info"].items())


@pytest.mark.parametrize(
    ("path", "body", "view"),
    [
        ("/api/project/layout/pid/V-101", {"x": 500.0, "y": 60.0}, "pid"),
        ("/api/project/layout/plot/V-101", {"x": 1000.0, "y": 2000.0, "z": 500.0}, "plot"),
    ],
)
def test_placement_returns_the_full_layout(path: str, body: dict[str, float], view: str) -> None:
    """api.place / api.placePlot type the reply as Layout {pfd, pid, plot} and
    read the stored position back from it."""
    r = c.put(path, json=body)
    assert r.status_code == 200
    layout = r.json()
    assert set(layout) >= {"pfd", "pid", "plot"}
    assert layout[view]["V-101"] == body


def test_plot_placement_without_elevation_is_422() -> None:
    """The plot PUT takes a full Vec3; the frontend always sends z."""
    assert c.put("/api/project/layout/plot/V-101", json={"x": 1.0, "y": 2.0}).status_code == 422


def test_unwired_unit_still_solves_and_draws_the_pfd() -> None:
    """A palette-added unit solves (it has no streams) and the PFD draws it."""
    _with_unwired_unit()
    assert c.post("/api/solve").status_code == 200
    r = c.get("/api/views/pfd.svg")
    assert r.status_code == 200
    assert 'data-tag="E-901"' in r.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/views/pid.svg"),
        ("get", "/api/views/plot.svg"),
        ("post", "/api/route"),
        ("get", "/api/views/iso"),
    ],
)
def test_unwired_unit_drawing_routes_are_422_not_500(method: str, path: str) -> None:
    """The P&ID chain cannot size or draw a unit with no connected streams:
    the views answer 422 naming the unit (the frontend shows the detail),
    never an unhandled 500."""
    _with_unwired_unit()
    r = TestClient(app, raise_server_exceptions=False).request(method.upper(), path)
    assert r.status_code == 422, r.text
    assert "E-901" in r.json()["detail"]


def test_unwired_unit_project_scoped_pid_is_422() -> None:
    """Same mapping on the project-scoped twin (one core, one handler)."""
    _with_unwired_unit()
    projects = c.get("/api/projects").json()["projects"]
    pid = next(p["id"] for p in projects if p["name"] == "default")
    r = TestClient(app, raise_server_exceptions=False).get(f"/api/projects/{pid}/views/pid.svg")
    assert r.status_code == 422, r.text
    assert "E-901" in r.json()["detail"]
