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


def test_thermo_recommend_matches_tool_payload() -> None:
    """T-08: the route and the recommend_thermo tool return identical rankings."""
    from ngdesign.flowsheets import slice as slice_fs
    from ngdesign.thermo import advisor

    r = c.get("/api/thermo/recommend")
    assert r.status_code == 200
    assert r.json() == advisor.payload(slice_fs.build())
    recs = r.json()["recommendations"]
    assert recs[0]["id"] in ("pr", "srk")
    assert all(rec["status"] != "experimental" for rec in recs)


def test_thermo_models_marks_experimental_unselectable() -> None:
    """Issue #154: experimental rows stay registered and listed, but selectable: false
    with the row's refusal reason (status + l0_note/references)."""
    r = c.get("/api/thermo/models")
    assert r.status_code == 200
    models = {m["id"]: m for m in r.json()["models"]}
    assert len(models) == len(registry.available("thermo"))
    assert models["pr"]["selectable"] is True
    assert "refusal_reason" not in models["pr"]
    # pc_saft left the list in T-15c: promoted to provisional, it selects and ranks
    # like any other provisional row (assessed misses per docs/validation.md).
    for rid in ("hoc_dimer", "eos_cg"):
        assert models[rid]["selectable"] is False, rid
        assert "experimental" in models[rid]["refusal_reason"]
    # Placeholder rows carry their refusal reason (status + l0_note).
    assert "not implemented" in models["eos_cg"]["refusal_reason"]
