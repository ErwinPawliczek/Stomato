"""C-4 regression: the plot placement route must stay registered ahead of the
{view}/{tag} catch-all.

Starlette matches routes in registration order, and app.py registers the plot
route before the catch-all deliberately (see the comment in routes): if the
order ever flips, PUT /api/project/layout/plot/{tag} is captured by the
{view}/{tag} route as view="plot", which 422s (view is Literal['pfd','pid'])
and would corrupt layout.pfd if the Literal ever widened. tests/api/test_plot.py
exercises plot placement end-to-end; this file pins the routing contract itself.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def test_plot_placement_lands_in_layout_plot_not_the_catch_all() -> None:
    _reset()
    r = c.put("/api/project/layout/plot/V-101", json={"x": 1000.0, "y": 2000.0, "z": 3000.0})
    assert r.status_code == 200, r.text
    layout = c.get("/api/project").json()["layout"]
    assert layout["plot"]["V-101"] == {"x": 1000.0, "y": 2000.0, "z": 3000.0}
    # A shadowing catch-all would have stored it under the wrong view dict.
    assert layout["pfd"] == {}
    assert layout["pid"] == {}


def test_plot_and_pid_placements_of_one_tag_coexist() -> None:
    """The two routes write different dicts of the same layout: nothing is lost."""
    _reset()
    assert c.put("/api/project/layout/pid/V-101", json={"x": 5.0, "y": 6.0}).status_code == 200
    assert c.put("/api/project/layout/plot/V-101", json={"x": 1.0, "y": 2.0, "z": 3.0}).status_code == 200
    layout = c.get("/api/project").json()["layout"]
    assert layout["pid"]["V-101"] == {"x": 5.0, "y": 6.0}
    assert layout["plot"]["V-101"] == {"x": 1.0, "y": 2.0, "z": 3.0}
