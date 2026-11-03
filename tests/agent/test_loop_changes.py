"""The loop forwards each mutating tool's change (diff) and attributes it to the actor."""

from __future__ import annotations

from typing import Any

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.loop import run_conversation
from ngdesign.agent.model import ModelResponse, ScriptedModel, ToolUseRequest
from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.store import DbProjectStore, create_project


def test_tool_result_carries_change_and_undo_reverts_it() -> None:
    row = create_project(name="t", owner="local", project=Project(name="t", flowsheet=slice_fs.build()))
    store = DbProjectStore(row.id)
    place = {
        "kind": "cooler",
        "tag": "E-201",
        "params": None,
        "position": None,
        "grid": {"q": 1, "r": 0},
        "view": None,
    }
    model = ScriptedModel(
        script=[
            ModelResponse("", (ToolUseRequest("c1", "place_unit", place),), "tool_use", 1, 1),
            ModelResponse("", (ToolUseRequest("c2", "undo", {}),), "tool_use", 1, 1),
            ModelResponse("done", (), "end_turn", 1, 1),
        ]
    )
    events: list[dict[str, Any]] = []
    run_conversation(model, store, DEFAULT_ENGINE, "add a cooler", [], events.append, actor="agent:conv-1")
    results = [e for e in events if e["type"] == "tool_result"]
    placed, undone = results
    assert placed["ok"] and placed["change"]["actor"] == "agent:conv-1"
    assert placed["change"]["diff"]["units"]["added"][0]["tag"] == "E-201"
    assert "+ unit E-201 (cooler)" in placed["change"]["lines"]
    assert undone["ok"] and undone["change"]["kind"] == "undo"
    assert "E-201" not in {u.tag for u in store.get().flowsheet.units}
    assert sum(1 for e in events if e["type"] == "project_changed") == 2
