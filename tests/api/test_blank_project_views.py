"""A new blank project (no units, no streams) is a normal state in the Home
flow: every drawing route answers it without a 500. The PFD draws an empty
sheet; the routed views (plot plan, re-route, isometrics) have nothing to route
between and say so as a 422 with the reason."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ngdesign.api.app import app
from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.render.pfd_svg import render_pfd_svg

c = TestClient(app)


def _blank_project() -> str:
    response = c.post("/api/projects", json={"name": "Blank views check"})
    if response.status_code == 409:  # re-run in the same database
        rows: list[dict[str, Any]] = c.get("/api/projects").json()["projects"]
        existing: str = next(p["id"] for p in rows if p["name"] == "Blank views check")
        return existing
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


def test_render_pfd_svg_of_an_empty_flowsheet_is_an_empty_sheet() -> None:
    blank = Flowsheet(name="blank", units=[], streams=[])
    solved = SolvedFlowsheet(flowsheet=blank, streams={}, units={}, converged=True, iterations=0)
    svg = render_pfd_svg(solved)
    assert svg.startswith("<svg") and "data-tag" not in svg


def test_blank_project_pfd_and_pid_render() -> None:
    pid = _blank_project()
    for view in ("pfd", "pid"):
        response = c.get(f"/api/projects/{pid}/views/{view}.svg")
        assert response.status_code == 200, (view, response.text)
        assert response.text.startswith("<svg")
    assert c.get(f"/api/v1/projects/{pid}/exports/pfd.svg").status_code == 200


def test_blank_project_routed_views_are_422_with_the_reason() -> None:
    pid = _blank_project()
    for method, path in (
        ("GET", "/views/plot.svg"),
        ("POST", "/route"),
        ("GET", "/views/iso"),
    ):
        response = c.request(method, f"/api/projects/{pid}{path}")
        assert response.status_code == 422, (path, response.text)
        assert "no equipment" in response.json()["detail"]
