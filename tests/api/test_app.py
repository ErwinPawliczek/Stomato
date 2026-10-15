from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api.app import app

c = TestClient(app)


def test_meta_lists_registered_plugins() -> None:
    m = c.get("/api/meta").json()
    assert sorted(set(m)) == sorted(map(str, registry.KINDS))
    # Live-registered thermo plugins: the names POST /api/solve honors.
    assert ["nrtl", "pr", "pr78", "srk"] == sorted(m["thermo"])
    # Every registered unit kind is visible to the frontend.
    assert {
        "air_cooler",
        "cooler",
        "compressor",
        "heater",
        "jt_valve",
        "mdea_absorber",
        "mdea_regenerator",
        "mixer",
        "pump",
        "scrubber",
        "separator_3phase",
        "shell_tube",
        "splitter",
        "teg_contactor",
    } == set(m["unit"])
    for names in m.values():
        assert isinstance(names, list) and names and names == sorted(names)


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
