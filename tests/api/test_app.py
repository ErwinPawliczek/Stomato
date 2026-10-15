from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def test_health() -> None:
    assert c.get("/api/health").json() == {"status": "ok"}


def test_project_roundtrip_and_placement() -> None:
    c.post("/api/project/reset")
    p = c.get("/api/project").json()
    assert p["name"] == "slice"
    r = c.put("/api/project/layout/pfd/V-101", json={"x": 10, "y": 20})
    assert r.json()["pfd"]["V-101"] == {"x": 10, "y": 20}
    assert c.put("/api/project", json=c.get("/api/project").json()).status_code == 200
    assert c.get("/api/project").json()["layout"]["pfd"]["V-101"]["x"] == 10
