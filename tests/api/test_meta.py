"""GET /api/meta contract tests (wave-2 surfacing spec, art_Y5Arnw5b).

The endpoint is the frontend's discovery seam: it must name every
live-registered plugin, including wave-1 additions (mdea_*, srk, pr78, nrtl),
or the UI cannot enumerate the engine's capabilities.
"""

from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api.app import app

c = TestClient(app)


def test_meta_lists_all_kinds() -> None:
    r = c.get("/api/meta")
    assert r.status_code == 200
    meta = r.json()
    assert sorted(meta) == sorted(registry.KINDS)
    for names in meta.values():
        for name in names:
            assert isinstance(name, str) and name


def test_meta_lists_all_registered_unit_kinds() -> None:
    units = set(c.get("/api/meta").json()["unit"])
    expected = {
        "compressor",
        "heater",
        "cooler",
        "air_cooler",
        "shell_tube",
        "jt_valve",
        "mixer",
        "pump",
        "separator_3phase",
        "scrubber",
        "splitter",
        "teg_contactor",
        "mdea_absorber",
        "mdea_regenerator",
    }
    assert expected <= units, f"missing unit kinds: {sorted(expected - units)}"


def test_meta_lists_all_thermo_names() -> None:
    thermo = c.get("/api/meta").json()["thermo"]
    assert set(registry.available("thermo")) <= set(thermo)
    assert {"pr", "srk", "pr78", "nrtl"} <= set(thermo)


def test_meta_matches_live_registry() -> None:
    meta = c.get("/api/meta").json()
    for kind in registry.KINDS:
        assert meta[kind] == registry.available(kind)
