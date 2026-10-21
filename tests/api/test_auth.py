"""P3-01 auth acceptance: open mode without STOMATO_API_TOKENS, bearer tokens
mapping to owners, owner scoping of project lists, 401s, and /api/health open.
Tokens ride the environment; no test ever prints one."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ngdesign.api import auth
from ngdesign.api.app import app
from ngdesign.store import reset_engine

c = TestClient(app)


@pytest.fixture()
def token_mode(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Two tokens (alice/bob); owners never leak into assertions as tokens."""
    monkeypatch.setenv("STOMATO_API_TOKENS", "alice-token:alice,bob-token:bob")
    auth.reset_auth_cache()
    return {"alice": "alice-token", "bob": "bob-token"}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_open_mode_needs_no_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOMATO_API_TOKENS", raising=False)
    auth.reset_auth_cache()
    assert c.get("/api/projects").status_code == 200
    assert c.get("/api/health").json() == {"status": "ok"}


def test_token_mode_requires_a_bearer_header(token_mode: dict[str, str]) -> None:
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/projects", headers={"Authorization": "Basic nope"}).status_code == 401
    assert c.get("/api/projects", headers=_headers("wrong-token")).status_code == 401
    assert c.get("/api/health").status_code == 200  # the liveness probe stays open


def test_token_maps_to_an_owner(token_mode: dict[str, str]) -> None:
    response = c.get("/api/projects", headers=_headers(token_mode["alice"]))
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_owners_see_only_their_projects(token_mode: dict[str, str]) -> None:
    slice_body = c.get("/api/project", headers=_headers(token_mode["alice"])).json()
    created = c.post(
        "/api/projects",
        json={"name": "alice-only", "project": slice_body},
        headers=_headers(token_mode["alice"]),
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    alice_list = c.get("/api/projects", headers=_headers(token_mode["alice"])).json()["projects"]
    bob_list = c.get("/api/projects", headers=_headers(token_mode["bob"])).json()["projects"]
    # Alice's GET /api/project created her 'default' project first; Bob has none.
    assert [p["name"] for p in alice_list] == ["default", "alice-only"]
    assert bob_list == []

    # Bob cannot read, write or delete Alice's project.
    assert c.get(f"/api/projects/{pid}", headers=_headers(token_mode["bob"])).status_code == 403
    assert (
        c.put(
            f"/api/projects/{pid}",
            json=c.get(f"/api/projects/{pid}", headers=_headers(token_mode["alice"])).json()["project"],
            headers=_headers(token_mode["bob"]),
        ).status_code
        == 403
    )
    assert c.delete(f"/api/projects/{pid}", headers=_headers(token_mode["bob"])).status_code == 403


def test_malformed_tokens_config_is_a_loud_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOMATO_API_TOKENS", "just-a-token-no-owner")
    auth.reset_auth_cache()
    with pytest.raises(ValueError, match="entry 1"):
        auth.auth_state()


def test_engine_reset_is_independent_of_the_auth_cache() -> None:
    reset_engine()  # auth cache and DB engine must not interfere
    auth.reset_auth_cache()
