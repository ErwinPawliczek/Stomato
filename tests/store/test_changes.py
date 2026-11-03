"""The project change log (docs/agentic-layer.md section 3): every body write is
an undoable change; history is linear; history moves refuse on a foreign write."""

from __future__ import annotations

import pytest
from sqlmodel import select

from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.store import (
    DbProjectStore,
    NothingToMove,
    ProjectConflict,
    create_project,
    session,
)
from ngdesign.store import changes as change_log
from ngdesign.store.models import ChangeRow


def _store() -> tuple[DbProjectStore, Project]:
    project = Project(name="p", flowsheet=slice_fs.build())
    row = create_project(name="p", owner="local", project=project)
    return DbProjectStore(row.id), project


def _renamed_flowsheet(project: Project, name: str) -> Project:
    return project.model_copy(update={"flowsheet": project.flowsheet.model_copy(update={"name": name})})


def test_commit_records_before_and_after() -> None:
    store, base = _store()
    edited = _renamed_flowsheet(base, "edited")
    change = store.commit(edited, op="test", actor="mcp", summary="edit one", args={"k": 1})
    assert change is not None
    assert change.seq == 1 and change.kind == "edit" and change.state == "applied"
    assert change.actor == "mcp" and change.args == {"k": 1}
    assert Project.model_validate_json(change.before) == base
    assert Project.model_validate_json(change.after) == edited
    assert store.get() == edited
    assert store.row().version == 2


def test_noop_write_records_nothing_but_bumps_version() -> None:
    store, base = _store()
    assert store.commit(base, op="test", actor="api", summary="same") is None
    assert store.changes() == []
    assert store.row().version == 2


def test_put_is_logged() -> None:
    store, base = _store()
    store.put(_renamed_flowsheet(base, "x"))
    (change,) = store.changes()
    assert change.op == "put" and change.actor == "api"


def test_undo_redo_round_trip() -> None:
    store, base = _store()
    one = _renamed_flowsheet(base, "one")
    two = _renamed_flowsheet(base, "two")
    store.commit(one, op="t", actor="a", summary="one")
    store.commit(two, op="t", actor="a", summary="two")
    undo = store.undo(actor="ui")
    assert undo.kind == "undo" and undo.target_seq == 2 and undo.summary == "Undo: two"
    assert store.get() == one
    store.undo(actor="ui")
    assert store.get() == base
    with pytest.raises(NothingToMove):
        store.undo(actor="ui")
    redo = store.redo(actor="ui")
    assert redo.target_seq == 1 and store.get() == one
    store.redo(actor="ui")
    assert store.get() == two
    with pytest.raises(NothingToMove):
        store.redo(actor="ui")


def test_new_edit_drops_redo_branch() -> None:
    store, base = _store()
    store.commit(_renamed_flowsheet(base, "one"), op="t", actor="a", summary="one")
    store.undo(actor="a")
    store.commit(_renamed_flowsheet(base, "other"), op="t", actor="a", summary="other")
    with pytest.raises(NothingToMove):
        store.redo(actor="a")
    states = {c.summary: c.state for c in store.changes() if c.kind == "edit"}
    assert states == {"one": "dropped", "other": "applied"}


def test_undo_refuses_after_unlogged_write() -> None:
    store, base = _store()
    store.commit(_renamed_flowsheet(base, "one"), op="t", actor="a", summary="one")
    with session() as db:  # a write that bypasses the log
        row = store.row()
        row.body_json = _renamed_flowsheet(base, "rogue").model_dump_json()
        db.add(row)
        db.commit()
    with pytest.raises(ProjectConflict, match="outside the recorded history"):
        store.undo(actor="a")


def test_changes_after_and_rename_logged() -> None:
    store, base = _store()
    store.commit(_renamed_flowsheet(base, "one"), op="t", actor="a", summary="one")
    store.rename("renamed")
    assert [c.seq for c in store.changes(after=1)] == [2]
    assert store.changes(after=1)[0].op == "rename"
    store.undo(actor="a")
    assert store.get().name == "p"


def test_history_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(change_log, "MAX_HISTORY", 3)
    store, base = _store()
    for i in range(5):
        store.commit(_renamed_flowsheet(base, f"v{i}"), op="t", actor="a", summary=f"v{i}")
    assert [c.seq for c in store.changes()] == [3, 4, 5]


def test_delete_cascades_changes() -> None:
    store, base = _store()
    store.commit(_renamed_flowsheet(base, "one"), op="t", actor="a", summary="one")
    store.delete()
    with session() as db:
        assert db.exec(select(ChangeRow)).all() == []
