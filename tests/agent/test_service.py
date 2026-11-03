"""ProjectService and the agentic-layer tools (docs/agentic-layer.md sections 2, 3, 5).

Runs on the real DbProjectStore (the conftest isolates a SQLite file per test)
so history, attribution and diffs are exercised end to end — no LLM, no network.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.service import HEX_SIZE, OpError, ProjectService, hex_centre
from ngdesign.agent.tools import TOOLS, run_tool, tool_definitions
from ngdesign.contracts import Project
from ngdesign.contracts.specs import DesignSpec
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.store import DbProjectStore, create_project


def _store() -> DbProjectStore:
    row = create_project(name="t", owner="local", project=Project(name="t", flowsheet=slice_fs.build()))
    return DbProjectStore(row.id)


def _svc(actor: str = "test") -> ProjectService:
    return ProjectService(_store(), DEFAULT_ENGINE, actor=actor)


def _ok(store: DbProjectStore, tool: str, **tool_input: Any) -> dict[str, Any]:
    outcome = run_tool(tool, tool_input, store, DEFAULT_ENGINE, actor="agent:test")
    assert outcome.ok, f"{tool}: {outcome.error}"
    return outcome.payload()


def test_place_unit_on_grid_records_undoable_change() -> None:
    svc = _svc()
    out = svc.place_unit("separator_3phase", grid={"q": 2, "r": -1})
    tag = out["added"]
    assert tag.startswith("V-") and tag != "V-101"  # next free tag from the P&ID symbol
    xy = svc.project().layout.pfd[tag]
    assert xy.x == pytest.approx(HEX_SIZE * 3.0)
    assert xy.y == pytest.approx(HEX_SIZE * math.sqrt(3.0) * 0.0)
    change = svc.last_change
    assert change is not None and change["actor"] == "test" and change["op"] == "place_unit"
    assert change["diff"]["units"]["added"][0]["tag"] == tag
    assert change["diff"]["layout"][0]["key"] == tag
    svc.undo()
    assert tag not in {u.tag for u in svc.project().flowsheet.units}
    assert tag not in svc.project().layout.pfd
    svc.redo()
    assert tag in {u.tag for u in svc.project().flowsheet.units}


def test_hex_centre_matches_frontend_lattice() -> None:
    # frontend/src/hexGrid.ts: x = 1.5 s q, y = sqrt(3) s (r + q/2)
    xy = hex_centre(1, 1)
    assert xy.x == pytest.approx(60.0) and xy.y == pytest.approx(40.0 * math.sqrt(3.0) * 1.5)


def test_position_and_grid_are_exclusive() -> None:
    with pytest.raises(OpError) as err:
        _svc().place_unit("separator_3phase", position={"x": 1, "y": 2}, grid={"q": 0, "r": 0})
    assert err.value.code == "bad_position"


def test_unknown_kind_and_unit_name_the_valid_ones() -> None:
    svc = _svc()
    with pytest.raises(OpError) as err:
        svc.place_unit("warp_drive")
    assert err.value.code == "unknown_kind"
    with pytest.raises(OpError) as err:
        svc.configure_unit("X-999", {"a": 1})
    assert err.value.code == "unknown_unit" and err.value.status == 404 and "K-101" in err.value.message


def test_set_cell_converts_units_and_checks_dimension() -> None:
    svc = _svc()
    out = svc.set_cell("S-001.feed.T", 25, "degC")
    assert out["value"] == pytest.approx(298.15) and out["unit"] == "K"
    svc.set_cell("K-101.params.P_out", 65, "bar")
    assert svc.project().flowsheet.units[1].params["P_out"] == pytest.approx(6.5e6)
    with pytest.raises(OpError) as err:
        svc.set_cell("K-101.params.P_out", 65, "degC")
    assert err.value.code == "unit_mismatch"
    with pytest.raises(OpError) as err:
        svc.set_cell("K-101.params.nope.deeper", 1)
    assert err.value.code == "unknown_address"
    assert svc.last_change is not None and svc.last_change["summary"] == "Set K-101.params.P_out = 65 bar"


def test_composition_cell_rescales_the_rest() -> None:
    svc = _svc()
    svc.set_cell("S-001.feed.composition.C1", 0.8)
    comp = next(s for s in svc.project().flowsheet.streams if s.id == "S-001").feed
    assert comp is not None and sum(comp.composition.values()) == pytest.approx(1.0)


def test_edits_keep_design_specs() -> None:
    """Regression: the B-08 rebuild dropped design specs/solver options on every edit."""
    svc = _svc()
    svc.add_design_spec(
        {
            "id": "DS-1",
            "target": "S-003.T",
            "value": 400.0,
            "manipulated": "K-101.params.P_out",
            "lower": 5e6,
            "upper": 8e6,
            "tolerance": None,
        }
    )
    svc.configure_unit("E-101", {"dP": 30000.0})
    svc.set_thermo("srk")
    specs = svc.project().flowsheet.design_specs
    assert [s.id for s in specs] == ["DS-1"] and isinstance(specs[0], DesignSpec)
    svc.delete_design_spec("DS-1")
    assert svc.project().flowsheet.design_specs == []


def test_connect_rejects_port_in_use_without_writing() -> None:
    svc = _svc()
    version = svc.store.row().version  # type: ignore[attr-defined]
    with pytest.raises(OpError) as err:
        svc.connect("V-101", "gas_out", "K-101", "inlet", stream_id="S-099")
    assert err.value.code == "invalid_project" and "connected twice" in err.value.message
    assert svc.store.row().version == version  # type: ignore[attr-defined]


def test_update_and_delete_stream() -> None:
    svc = _svc()
    svc.update_stream("S-001", service="PG", feed={"T": 300.0, "P": None})
    s1 = svc.stream("S-001")
    assert s1["service"] == "PG" and s1["feed"]["T"] == 300.0
    with pytest.raises(OpError) as err:
        svc.update_stream("S-002", feed={"T": 300.0})
    assert err.value.code == "not_a_feed"
    svc.delete_stream("S-011")
    assert "S-011" not in {s.id for s in svc.project().flowsheet.streams}


def test_delete_unit_drops_streams_and_placements() -> None:
    svc = _svc()
    svc.move_unit("E-102", position={"x": 10, "y": 20})
    out = svc.delete_unit("E-102")
    assert out["dropped_streams"] == ["S-009", "S-010"]
    assert "E-102" not in svc.project().layout.pfd


def test_results_read_with_units_and_explain() -> None:
    svc = _svc()
    results = svc.results()
    assert results["converged"] is True and results["status"] == "converged"
    t_k = svc.read("S-003.T")
    assert t_k["unit"] == "K"
    t_c = svc.read("S-003.T", "degC")
    assert t_c["value"] == pytest.approx(t_k["value"] - 273.15)
    kw = svc.read("K-101.power_W", "kW")
    assert kw["value"] == pytest.approx(kw["si_value"] / 1000.0)
    with pytest.raises(OpError) as err:
        svc.read("S-003.T", "bar")
    assert err.value.code == "unit_mismatch"
    explained = svc.explain("S-003.T")
    assert explained["value"] == pytest.approx(t_k["value"])
    assert explained["steps"] and explained["inputs"]
    assert explained["text"].startswith("S-003.T = ")
    with pytest.raises(OpError) as err:
        svc.explain("S-003.no_such_prop")
    assert err.value.code == "not_traced" and "T" in err.value.details["have"]


def test_catalogue_tools() -> None:
    store = _store()
    cat = _ok(store, "list_catalogue", section="all")
    assert {"units", "components", "thermo"} <= set(cat)
    kinds = {u["kind"]: u for u in cat["units"]}
    assert kinds["compressor"]["registered"] is True and "inlet" in kinds["compressor"]["inlet_ports"]
    full = _ok(store, "describe_unit_kind", kind="compressor")
    assert "example_params" in full and full["implemented_levels"]


def test_tools_attribute_changes_and_undo() -> None:
    store = _store()
    placed = _ok(
        store, "place_unit", kind="cooler", tag=None, params=None, position=None, grid=None, view=None
    )
    assert placed["change"]["actor"] == "agent:test" and placed["change"]["seq"] == 1
    _ok(store, "set_cell", address="E-101.params.dP", value=0.3, unit="bar")
    history = _ok(store, "list_changes", after=None, limit=None)["changes"]
    assert [c["op"] for c in history] == ["place_unit", "set_cell"]
    undone = _ok(store, "undo")
    assert undone["undo"] == 2 and undone["change"]["kind"] == "undo"
    nothing = run_tool("redo", {}, store, DEFAULT_ENGINE)
    assert nothing.ok
    nothing = run_tool("redo", {}, store, DEFAULT_ENGINE)
    assert not nothing.ok and nothing.code == "nothing_to_redo"


def test_read_results_and_explain_tools() -> None:
    store = _store()
    summary = _ok(store, "read_results", address=None, unit=None)
    assert summary["converged"] is True
    one = _ok(store, "read_results", address="S-001.P", unit="bar")
    assert one["unit"] == "bar"
    explained = _ok(store, "explain_value", address="K-101.power_W")
    assert explained["unit"] == "W"


def _strict(schema: dict[str, Any], where: str) -> None:
    """Anthropic strict tools: every object closed and every property required."""
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            _strict(sub, where)
        return
    if schema.get("type") == "object" and "properties" in schema:
        assert schema.get("additionalProperties") is False, where
        assert sorted(schema["required"]) == sorted(schema["properties"]), where
        for name, sub in schema["properties"].items():
            _strict(sub, f"{where}.{name}")


def test_every_tool_schema_is_strict_and_cached_once() -> None:
    defs = tool_definitions()
    assert [d["name"] for d in defs] == [t.name for t in TOOLS]
    assert len({d["name"] for d in defs}) == len(defs)
    for d in defs:
        _strict(d["input_schema"], d["name"])
    assert [i for i, d in enumerate(defs) if "cache_control" in d] == [len(defs) - 1]
    # The B-08 prefix is unchanged (prompt-cache stability, existing clients).
    assert [d["name"] for d in defs[:17]] == [
        "get_project", "list_unit_kinds", "list_components", "add_unit", "add_feed", "connect",
        "set_params", "remove_unit", "disconnect", "set_thermo", "recommend_thermo", "solve",
        "read_stream", "read_unit", "read_variable", "case_study", "render",
    ]  # fmt: skip
