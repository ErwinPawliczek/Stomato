"""Multi-project API: the template catalogue, create (blank / template / copy /
body), rename, open, delete, and the owner checks on each."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign.api import auth
from ngdesign.api.app import app
from ngdesign.flowsheets import slice as slice_fs

c = TestClient(app)


def _create(**body: Any) -> dict[str, Any]:
    response = c.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def _names() -> list[str]:
    return [p["name"] for p in c.get("/api/projects").json()["projects"]]


def test_templates_catalogue_lists_blank_first_with_sizes() -> None:
    templates = c.get("/api/templates").json()["templates"]
    ids = [t["id"] for t in templates]
    assert ids[0] == "blank"
    assert {"slice", "amine_loop", "mea_amine_loop"} <= set(ids)
    by_id = {t["id"]: t for t in templates}
    assert by_id["blank"]["units"] == 0 and by_id["blank"]["streams"] == 0
    built = slice_fs.build()
    assert by_id["slice"]["units"] == len(built.units)
    assert by_id["slice"]["streams"] == len(built.streams)
    assert all(t["title"] and t["description"] for t in templates)


def test_create_blank_is_the_default_source() -> None:
    created = _create(name="Empty one")
    assert created["template"] == "blank"
    assert created["project"]["name"] == "Empty one"
    assert created["project"]["flowsheet"]["units"] == []
    assert created["project"]["flowsheet"]["streams"] == []
    assert created["opened_at"] is None


def test_create_from_template_builds_that_flowsheet() -> None:
    created = _create(name="Dehy", template="slice")
    assert created["template"] == "slice"
    assert created["project"]["name"] == "Dehy"
    assert created["project"]["flowsheet"] == slice_fs.build().model_dump(mode="json")
    # The new project solves on its own scoped route like any other.
    assert c.post(f"/api/projects/{created['id']}/solve").status_code == 200


def test_unknown_template_is_422_naming_the_catalogue() -> None:
    response = c.post("/api/projects", json={"name": "x", "template": "nope"})
    assert response.status_code == 422
    assert "nope" in response.json()["detail"] and "slice" in response.json()["detail"]
    assert "x" not in _names()


def test_more_than_one_source_is_422() -> None:
    response = c.post("/api/projects", json={"name": "x", "template": "slice", "from_project": "abc"})
    assert response.status_code == 422


def test_blank_and_whitespace_names_are_422_and_names_are_trimmed() -> None:
    assert c.post("/api/projects", json={"name": "   "}).status_code == 422
    assert _create(name="  Padded  ")["name"] == "Padded"


def test_copy_an_existing_project_keeps_its_body_and_layout() -> None:
    source = _create(name="Original", template="slice")
    placed = c.put(f"/api/projects/{source['id']}/layout/pfd/K-101", json={"x": 5.0, "y": 6.0})
    assert placed.status_code == 200
    copy = _create(name="Copy", from_project=source["id"])
    assert copy["id"] != source["id"]
    assert copy["template"] == "slice"
    assert copy["project"]["name"] == "Copy"
    assert copy["project"]["layout"]["pfd"]["K-101"] == {"x": 5.0, "y": 6.0}
    assert copy["project"]["flowsheet"] == source["project"]["flowsheet"]
    # Independent afterwards: editing the copy leaves the original alone.
    c.put(f"/api/projects/{copy['id']}/layout/pfd/K-101", json={"x": 9.0, "y": 9.0})
    original = c.get(f"/api/projects/{source['id']}").json()
    assert original["project"]["layout"]["pfd"]["K-101"] == {"x": 5.0, "y": 6.0}


def test_copy_of_unknown_project_is_404() -> None:
    assert c.post("/api/projects", json={"name": "x", "from_project": "missing"}).status_code == 404


def test_create_with_duplicate_name_is_409() -> None:
    _create(name="Twin")
    assert c.post("/api/projects", json={"name": "Twin", "template": "slice"}).status_code == 409


def test_rename_moves_row_and_body_name_and_bumps_version() -> None:
    created = _create(name="Before", template="slice")
    response = c.patch(f"/api/projects/{created['id']}", json={"name": "After"})
    assert response.status_code == 200
    renamed = response.json()
    assert renamed["name"] == "After"
    assert renamed["project"]["name"] == "After"
    assert renamed["version"] == created["version"] + 1
    assert renamed["project"]["flowsheet"] == created["project"]["flowsheet"]
    assert "Before" not in _names() and "After" in _names()


def test_rename_to_own_name_is_ok_and_to_taken_name_is_409() -> None:
    a = _create(name="A")
    _create(name="B")
    assert c.patch(f"/api/projects/{a['id']}", json={"name": "A"}).status_code == 200
    clash = c.patch(f"/api/projects/{a['id']}", json={"name": "B"})
    assert clash.status_code == 409
    assert c.get(f"/api/projects/{a['id']}").json()["name"] == "A"
    assert c.patch(f"/api/projects/{a['id']}", json={"name": ""}).status_code == 422
    assert c.patch("/api/projects/missing", json={"name": "Z"}).status_code == 404


def test_open_stamps_opened_at_without_bumping_version() -> None:
    created = _create(name="Opened", template="slice")
    response = c.post(f"/api/projects/{created['id']}/open")
    assert response.status_code == 200
    opened = response.json()
    assert opened["opened_at"] is not None
    assert opened["version"] == created["version"]
    assert opened["updated_at"] == created["updated_at"]
    assert opened["project"] == created["project"]
    assert c.post("/api/projects/missing/open").status_code == 404


def test_delete_removes_only_that_project() -> None:
    keep = _create(name="Keep")
    drop = _create(name="Drop")
    assert c.delete(f"/api/projects/{drop['id']}").json() == {"deleted": True}
    assert _names() == ["Keep"]
    assert c.get(f"/api/projects/{keep['id']}").status_code == 200


@pytest.fixture()
def two_owners(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, str], dict[str, str]]:
    monkeypatch.setenv("STOMATO_API_TOKENS", "alice-token:alice,bob-token:bob")
    auth.reset_auth_cache()
    return {"Authorization": "Bearer alice-token"}, {"Authorization": "Bearer bob-token"}


def test_foreign_owner_cannot_rename_open_or_copy(two_owners: tuple[dict[str, str], dict[str, str]]) -> None:
    alice, bob = two_owners
    created = c.post("/api/projects", json={"name": "Alice's", "template": "slice"}, headers=alice)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert c.patch(f"/api/projects/{pid}", json={"name": "Mine now"}, headers=bob).status_code == 403
    assert c.post(f"/api/projects/{pid}/open", headers=bob).status_code == 403
    copy = c.post("/api/projects", json={"name": "Stolen", "from_project": pid}, headers=bob)
    assert copy.status_code == 403
    # Names are unique per owner, not globally.
    assert c.post("/api/projects", json={"name": "Alice's"}, headers=bob).status_code == 201
    assert [p["name"] for p in c.get("/api/projects", headers=bob).json()["projects"]] == ["Alice's"]
