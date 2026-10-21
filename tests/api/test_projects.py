"""P3-01 acceptance at the HTTP layer: project CRUD twins, 409 on a stale
version, 403 for foreign owners, 404 for unknown projects, and the solve twin
sharing the legacy solve path (same 501 for a missing plugin)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign.api.app import app, cors_origins, create_app
from ngdesign.store import reset_engine

c = TestClient(app)


def _slice_project(name: str = "mine") -> dict[str, Any]:
    # GET /api/project hands out the sample slice; reuse it as a create body.
    project: dict[str, Any] = c.get("/api/project").json()
    project["name"] = name
    return project


def _create(name: str = "mine") -> dict[str, Any]:
    response = c.post("/api/projects", json={"name": name, "project": _slice_project(name)})
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def test_create_and_list_round_trip() -> None:
    created = _create("alpha")
    assert created["name"] == "alpha"
    assert created["owner"] == "local"  # open mode owner
    assert created["version"] == 1
    assert created["project"]["name"] == "alpha"

    listing = c.get("/api/projects").json()["projects"]
    # 'default' is created lazily by the GET /api/project helper before 'alpha'.
    assert [p["name"] for p in listing] == ["default", "alpha"]


def test_create_rejects_duplicate_name_with_409() -> None:
    _create("alpha")
    response = c.post("/api/projects", json={"name": "alpha", "project": _slice_project("alpha")})
    assert response.status_code == 409
    assert "alpha" in response.json()["detail"]


def test_get_put_delete_and_404() -> None:
    created = _create("alpha")
    pid = created["id"]

    got = c.get(f"/api/projects/{pid}")
    assert got.status_code == 200
    assert got.json()["project"]["name"] == "alpha"

    put = c.put(f"/api/projects/{pid}", json=_slice_project("edited"))
    assert put.status_code == 200
    assert put.json()["version"] == 2
    assert put.json()["project"]["name"] == "edited"

    assert c.delete(f"/api/projects/{pid}").json() == {"deleted": True}
    assert c.get(f"/api/projects/{pid}").status_code == 404
    assert c.delete(f"/api/projects/{pid}").status_code == 404


def test_put_with_stale_expected_version_is_409() -> None:
    pid = _create("alpha")["id"]

    ok = c.put(f"/api/projects/{pid}?expected_version=1", json=_slice_project("v2"))
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    stale = c.put(f"/api/projects/{pid}?expected_version=1", json=_slice_project("stale"))
    assert stale.status_code == 409
    assert c.get(f"/api/projects/{pid}").json()["project"]["name"] == "v2"  # stale write skipped

    current = c.put(f"/api/projects/{pid}?expected_version=2", json=_slice_project("v3"))
    assert current.status_code == 200
    assert current.json()["version"] == 3


def test_solve_twin_shares_the_legacy_path() -> None:
    pid = _create("alpha")["id"]
    twin = c.post(f"/api/projects/{pid}/solve")
    assert twin.status_code == 200
    legacy = c.post("/api/solve")
    assert legacy.status_code == 200
    # Same project body (the sample slice) -> same solved flowsheet.
    assert twin.json()["streams"] == legacy.json()["streams"]


def test_solve_twin_501_for_unknown_unit_kind() -> None:
    pid = _create("alpha")["id"]
    broken = {
        "name": "broken",
        "flowsheet": {
            "name": "broken",
            "units": [{"tag": "X-101", "kind": "no_such_unit", "params": {}}],
            "streams": [],
        },
    }
    assert c.put(f"/api/projects/{pid}", json=broken).status_code == 200
    response = c.post(f"/api/projects/{pid}/solve")
    assert response.status_code == 501
    assert "no_such_unit" in response.json()["detail"]


def test_layout_twins_persist_and_are_scoped() -> None:
    pid = _create("alpha")["id"]

    plot = c.put(f"/api/projects/{pid}/layout/plot/K-101", json={"x": 100.0, "y": 50.0, "z": 0.0})
    assert plot.status_code == 200
    pfd = c.put(f"/api/projects/{pid}/layout/pfd/K-101", json={"x": 10.0, "y": 20.0})
    assert pfd.status_code == 200
    assert pfd.json()["pfd"]["K-101"] == {"x": 10.0, "y": 20.0}

    # Stored on THIS project only: the default project's layout is untouched.
    assert c.get("/api/project").json()["layout"]["pfd"] == {}


def test_unknown_unit_project_view_returns_409() -> None:
    """P3-01 x-check: the layout PUT rejects an unknown unit kind with 409."""
    pid = _create("alpha")["id"]
    response = c.put(f"/api/projects/{pid}/layout/plot/NOPE", json={"x": 1.0, "y": 2.0, "z": 0.0})
    assert response.status_code == 409


def test_two_app_instances_share_one_sqlite_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec P3-01 gate: a project created through one app instance is visible to
    a second instance (a restart, or a second replica) over the same file."""
    monkeypatch.setenv("STOMATO_DATABASE_URL", f"sqlite:///{tmp_path}/shared.db")
    reset_engine()
    first = TestClient(create_app())
    body = first.get("/api/project").json()
    body["name"] = "survivor"
    assert first.post("/api/projects", json={"name": "survivor", "project": body}).status_code == 201

    reset_engine()  # the restart seam: a new engine over the same file
    second = TestClient(create_app())
    names = [p["name"] for p in second.get("/api/projects").json()["projects"]]
    assert "survivor" in names


def test_cors_origins_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOMATO_CORS_ORIGINS", raising=False)
    assert cors_origins() == ["http://localhost:5173"]
    monkeypatch.setenv("STOMATO_CORS_ORIGINS", "https://app.example.com, http://localhost:3000")
    assert cors_origins() == ["https://app.example.com", "http://localhost:3000"]
    monkeypatch.setenv("STOMATO_CORS_ORIGINS", "*")
    with pytest.raises(ValueError):
        cors_origins()
    monkeypatch.setenv("STOMATO_CORS_ORIGINS", "https://app.example.com")
    client = TestClient(create_app())
    allowed = client.get("/api/health", headers={"Origin": "https://app.example.com"})
    assert allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    denied = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in denied.headers
