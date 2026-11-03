"""The structured project diff (docs/agentic-layer.md section 3)."""

from __future__ import annotations

from ngdesign.agent.diff import diff_lines, project_diff
from ngdesign.contracts import XY, Project, UnitSpec
from ngdesign.flowsheets import slice as slice_fs


def _base() -> Project:
    return Project(name="p", flowsheet=slice_fs.build())


def test_identical_projects_have_empty_diff() -> None:
    assert project_diff(_base(), _base()) == {}
    assert diff_lines({}) == []


def test_unit_param_stream_thermo_and_layout_changes() -> None:
    a = _base()
    fs = a.flowsheet
    units = [
        u.model_copy(update={"params": {**u.params, "P_out": 6.0e6}}) if u.tag == "K-101" else u
        for u in fs.units
        if u.tag != "E-102"
    ] + [UnitSpec(tag="E-201", kind="cooler", params={})]
    streams = [
        s.model_copy(update={"service": "PL"}) if s.id == "S-002" else s
        for s in fs.streams
        if s.id not in ("S-009", "S-010")
    ]
    b_fs = fs.model_copy(update={"units": units, "streams": streams, "thermo": "srk"})
    b = a.model_copy(
        update={"flowsheet": b_fs, "layout": a.layout.model_copy(update={"pfd": {"E-201": XY(x=1, y=2)}})}
    )
    d = project_diff(a, b)
    assert d["units"]["added"] == [{"tag": "E-201", "kind": "cooler", "params": {}}]
    assert d["units"]["removed"] == [{"tag": "E-102", "kind": "shell_tube"}]
    assert d["units"]["changed"] == [
        {"tag": "K-101", "fields": {"params.P_out": {"from": 7.0e6, "to": 6.0e6}}}
    ]
    assert [s["id"] for s in d["streams"]["removed"]] == ["S-009", "S-010"]
    assert d["streams"]["changed"][0]["fields"]["service"]["to"] == "PL"
    assert d["thermo"] == {"from": "pr", "to": "srk"}
    assert d["layout"] == [{"view": "pfd", "key": "E-201", "from": None, "to": {"x": 1.0, "y": 2.0}}]
    lines = diff_lines(d)
    assert "+ unit E-201 (cooler)" in lines
    assert "~ K-101.params.P_out: 7000000.0 -> 6000000.0" in lines
    assert "~ thermo: pr -> srk" in lines
