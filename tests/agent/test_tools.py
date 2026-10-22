"""B-08 acceptance: every tool exercised without any LLM on the slice project.

- add/connect/set_params/remove round-trip the ``Project``: removing what was
  added restores the starting project exactly.
- Invalid kind, duplicate tag, unknown port and bad composition each come back
  as an ``error`` outcome (the model fixes its own mistakes; nothing raises),
  and a failed mutation never changes the stored project.
- ``solve`` on the slice converges; ``read_variable`` equals the solved result;
  ``case_study`` sweeps on copies and leaves the stored project unchanged;
  ``render`` returns the view URL plus P&ID counts.
"""

from __future__ import annotations

from typing import Any

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.tools import run_tool, tool_definitions
from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.thermo import advisor


class _Store:
    """In-memory ProjectStore for tool tests (the API injects the real one)."""

    def __init__(self, project: Project) -> None:
        self._project = project

    def get(self) -> Project:
        return self._project

    def put(self, project: Project) -> Project:
        self._project = project
        return project


def _store() -> _Store:
    return _Store(Project(name="slice", flowsheet=slice_fs.build()))


def _run(store: _Store, tool: str, **tool_input: Any) -> dict[str, Any]:
    outcome = run_tool(tool, tool_input, store, DEFAULT_ENGINE)
    assert outcome.ok, f"{tool}: expected ok, got error {outcome.error!r}"
    assert isinstance(outcome.result, dict)
    return outcome.result


def _run_err(store: _Store, tool: str, **tool_input: Any) -> str:
    outcome = run_tool(tool, tool_input, store, DEFAULT_ENGINE)
    assert not outcome.ok, f"{tool}: expected an error outcome, got {outcome.result!r}"
    assert isinstance(outcome.error, str)
    return outcome.error


def test_recommend_thermo_matches_advisor_payload() -> None:
    """T-08: the tool reads the current flowsheet and returns the advisor payload."""
    store = _store()
    result = _run(store, "recommend_thermo")
    assert result == advisor.payload(slice_fs.build())
    recs = result["recommendations"]
    assert recs[0]["id"] in ("pr", "srk")
    assert any("water" in w for w in recs[0]["warnings"])
    assert all(rec["status"] != "experimental" for rec in recs)


def test_tool_definitions_are_strict_and_closed() -> None:
    """The schema contract the SDK enforces: strict tools, no open objects."""
    defs = tool_definitions()
    names = [d["name"] for d in defs]
    assert len(names) == len(set(names)), "duplicate tool name"
    for d in defs:
        assert d["strict"] is True, d["name"]
        assert d["input_schema"]["additionalProperties"] is False, d["name"]
        assert d["input_schema"]["type"] == "object"


def test_add_connect_set_params_remove_round_trip() -> None:
    """The mutation tools replay the Project: removing the addition restores it."""
    store = _store()
    start = store.get().model_copy(deep=True)

    added = _run(store, "add_unit", tag="K-201", kind="compressor", params={"P_out": 7.5e6})
    assert added["added"] == "K-201"
    _run(
        store,
        "add_feed",
        stream_id="F-201",
        target_unit="K-201",
        target_port="inlet",
        T_K=303.15,
        P_Pa=5.0e6,
        molar_flow_mol_s=50.0,
        composition={"C1": 0.9, "C2": 0.05, "N2": 0.05},
    )
    _run(store, "connect", stream_id="S-201", source_unit="K-201", source_port="outlet")
    _run(store, "set_params", tag="K-201", params={"P_out": 8.0e6})
    assert [u.tag for u in store.get().flowsheet.units] == [
        *(u.tag for u in start.flowsheet.units),
        "K-201",
    ]

    _run(store, "disconnect", stream_id="S-201")
    _run(store, "disconnect", stream_id="F-201")
    removed = _run(store, "remove_unit", tag="K-201")
    assert removed["removed"] == "K-201"
    assert store.get() == start, "mutation round-trip did not restore the project"


def test_invalid_inputs_are_error_outcomes_that_change_nothing() -> None:
    """Every rejection is a model-visible error; the stored project is untouched."""
    store = _store()
    start = store.get().model_copy(deep=True)

    err = _run_err(store, "add_unit", tag="X-101", kind="no_such_unit", params={})
    assert "no_such_unit" in err
    err = _run_err(store, "add_unit", tag="V-101", kind="separator_3phase", params={})
    assert "duplicate unit tags" in err  # duplicate tag
    err = _run_err(
        store,
        "add_feed",
        stream_id="F-X",
        target_unit="K-101",
        target_port="nope",
        T_K=300.0,
        P_Pa=1e6,
        molar_flow_mol_s=1.0,
        composition={"C1": 1.0},
    )
    assert "nope" in err  # unknown port
    err = _run_err(
        store,
        "add_feed",
        stream_id="F-X",
        target_unit="K-101",
        target_port="inlet",
        T_K=300.0,
        P_Pa=1e6,
        molar_flow_mol_s=1.0,
        composition={"C1": 0.9, "Unobtanium": 0.1},
    )
    assert "Unobtanium" in err  # bad composition: component outside the slate
    err = _run_err(store, "connect", stream_id="S-X", source_unit="nope", source_port="outlet")
    assert "nope" in err  # unknown unit
    outcome = run_tool("no_such_tool", {}, store, DEFAULT_ENGINE)
    assert not outcome.ok and outcome.error is not None and "no_such_tool" in outcome.error

    assert store.get() == start, "a failed mutation changed the stored project"


def test_solve_converges_on_the_slice() -> None:
    result = _run(_store(), "solve")
    assert result["converged"] is True
    assert set(result["units"]) >= {"V-101", "K-101", "E-101"}
    assert set(result["streams"]) >= {"S-001", "S-002"}


def test_read_variable_equals_solved_result() -> None:
    store = _store()
    solved = _run(store, "solve")
    power = _run(store, "read_variable", address="K-101.power_W")
    assert power == {"address": "K-101.power_W", "value": solved["units"]["K-101"]["power_W"]}


def test_case_study_sweeps_copies_monotonically() -> None:
    """Higher discharge pressure costs more power; the stored project is unchanged."""
    store = _store()
    start = store.get().model_copy(deep=True)
    study = _run(
        store,
        "case_study",
        address="K-101.params.P_out",
        # From the slice's own 7.0 MPa upward: lower discharge pressures push the
        # TEG contactor's 7.0 lb/MMscf water spec below its equilibrium floor.
        values=[7.0e6, 7.5e6, 8.0e6, 8.5e6, 9.0e6],
        outputs=["K-101.power_W"],
    )
    assert study["address"] == "K-101.params.P_out"
    assert [row["value"] for row in study["rows"]] == [7.0e6, 7.5e6, 8.0e6, 8.5e6, 9.0e6]
    powers = [row["K-101.power_W"] for row in study["rows"]]
    assert all(b > a for a, b in zip(powers, powers[1:], strict=False)), powers
    assert store.get() == start, "case_study mutated the stored project"


def test_case_study_reports_bad_values_as_errors() -> None:
    outcome = run_tool(
        "case_study",
        {"address": "K-101.params.P_out", "values": [-1.0], "outputs": ["K-101.power_W"]},
        _store(),
        DEFAULT_ENGINE,
    )
    assert not outcome.ok and outcome.error is not None and "-1.0" in outcome.error


def test_render_returns_url_and_counts() -> None:
    store = _store()
    _run(store, "solve")
    pfd = _run(store, "render", view="pfd")
    assert pfd["url"] == "/api/views/pfd.svg"
    assert pfd["units"] >= 1 and pfd["lines"] >= 1 and pfd["instruments"] >= 1
    pid = _run(store, "render", view="pid")
    assert pid["url"] == "/api/views/pid.svg"


def test_list_tools_report_registry_and_slate() -> None:
    store = _store()
    kinds = _run(store, "list_unit_kinds")["kinds"]
    assert kinds["compressor"]["inlet_ports"] == ["inlet"]
    components = _run(store, "list_components")
    assert set(store.get().flowsheet.components) <= set(components["components"])


def test_set_thermo_round_trips() -> None:
    store = _store()
    result = _run(store, "set_thermo", name="nrtl")
    assert result == {"thermo": "nrtl"}
    assert store.get().flowsheet.thermo == "nrtl"
    err = _run_err(store, "set_thermo", name="no_such_thermo")
    assert "no_such_thermo" in err
