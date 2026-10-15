"""C-4 acceptance: the API rejects malformed project JSON and unknown paths without
corrupting the stored project.

Every rejected request is verified against the contract validators FastAPI runs on
PUT /api/project (pydantic models + flowsheet integrity checks) and, critically, the
probe-verified invariant that a 422 leaves the current project byte-for-byte
unchanged — no partial writes from malformed bodies.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _get_project() -> dict[str, Any]:
    r = c.get("/api/project")
    assert r.status_code == 200
    payload: dict[str, Any] = r.json()
    return payload


def _rejects(body: dict[str, Any] | str) -> None:
    """A malformed PUT /api/project answers 422 and changes nothing."""
    baseline = _get_project()
    if isinstance(body, str):
        r = c.put("/api/project", content=body.encode(), headers={"Content-Type": "application/json"})
    else:
        r = c.put("/api/project", json=body)
    assert r.status_code == 422, r.text
    assert c.get("/api/project").json() == baseline


def test_missing_project_name_is_422() -> None:
    _reset()
    _rejects({"flowsheet": {"name": "x", "units": [], "streams": []}})


def test_units_that_are_not_a_list_is_422() -> None:
    _reset()
    _rejects({"name": "x", "flowsheet": {"name": "x", "units": {}, "streams": []}})


def test_unit_with_unknown_kind_but_bad_shape_is_422() -> None:
    """Even before the plugin check, contract validators reject malformed units."""
    _reset()
    _rejects(
        {
            "name": "x",
            "flowsheet": {
                "name": "x",
                "units": [{"tag": "BAD TAG!", "kind": "compressor", "params": {}}],
                "streams": [],
            },
        }
    )


def test_stream_referencing_an_unknown_unit_is_422() -> None:
    """Flowsheet validation rejects streams wired to a unit tag that does not exist."""
    _reset()
    project = _get_project()
    project["flowsheet"]["streams"][0]["source"] = {"unit": "NOPE", "port": "out"}
    _rejects(project)


def test_raw_malformed_json_is_422() -> None:
    _reset()
    _rejects('{"name": "x", "flowsheet":')


def test_unknown_view_literal_on_placement_is_422() -> None:
    """Layout views are a closed Literal['pfd', 'pid', 'plot'] set; anything else 422s."""
    _reset()
    r = c.put("/api/project/layout/plotx/T-101", json={"x": 1.0, "y": 2.0})
    assert r.status_code == 422
    assert "literal_error" in r.text


def test_unknown_view_svg_is_404() -> None:
    """Each SVG view is a literal route; an unknown view name matches nothing -> 404."""
    _reset()
    assert c.get("/api/views/plotx.svg").status_code == 404
    assert c.get("/api/views/PFD.svg").status_code == 404


def test_unknown_project_paths_are_404() -> None:
    """The API serves one current project; project-addressed paths do not exist.

    Unknown project routes must 404 (route not found), not 405 (known path,
    wrong method) and not silently fall through to the catch-all placement
    route — a PUT to /api/project/<id>/layout/... must never match
    /api/project/layout/{view}/{tag}.
    """
    _reset()
    assert c.get("/api/project/does-not-exist").status_code == 404
    assert c.put("/api/project/does-not-exist", json={"name": "x"}).status_code == 404
    assert c.post("/api/frobnicate").status_code == 404


def test_placement_rejects_wrong_geometry_shapes() -> None:
    """pfd/pid take XY (z is extra_forbidden); plot takes Vec3 (z required)."""
    _reset()
    assert c.put("/api/project/layout/pfd/V-101", json={"x": 1.0, "y": 2.0, "z": 3.0}).status_code == 422
    assert c.put("/api/project/layout/plot/V-101", json={"x": 1.0, "y": 2.0}).status_code == 422
    # Neither rejected request left a partial placement behind.
    layout = _get_project()["layout"]
    assert layout["pfd"] == {}
    assert layout["plot"] == {}
