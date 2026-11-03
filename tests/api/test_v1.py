"""Public REST API v1 (docs/agentic-layer.md section 4): one success and one error
case per endpoint, the error envelope on every failure, ``{result, change}`` on
every mutation, and the change history behind undo/redo and the change stream."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign.api import routes_jobs
from ngdesign.api.app import app
from ngdesign.jobs.worker import run_worker

c = TestClient(app)
V1 = "/api/v1"


def _create(name: str = "p", template: str = "slice") -> str:
    r = c.post(f"{V1}/projects", json={"name": name, "template": template})
    assert r.status_code == 201, r.text
    pid: str = r.json()["id"]
    return pid


def _err(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    body: dict[str, Any] = r.json()
    assert set(body) == {"error"}, body
    assert body["error"]["code"] == code, body
    error: dict[str, Any] = body["error"]
    assert error["message"]
    return error


@pytest.fixture
def pid() -> str:
    return _create()


# --- meta and catalogue -----------------------------------------------------------------------


def test_index_and_tools() -> None:
    assert c.get(V1).json()["version"] == "1"
    names = [t["name"] for t in c.get(f"{V1}/tools").json()]
    assert {"place_unit", "set_cell", "explain_value", "undo"} <= set(names)
    _err(c.get(f"{V1}/no-such-route"), 404, "not_found")


def test_catalogue() -> None:
    units = c.get(f"{V1}/catalogue/units", params={"registered": True}).json()["units"]
    assert units and all(u["registered"] for u in units)
    comp = c.get(f"{V1}/catalogue/units/compressor").json()
    assert comp["inlet_ports"] == ["inlet"] and "example_params" in comp
    _err(c.get(f"{V1}/catalogue/units/warp_drive"), 404, "unknown_kind")
    ids = {x["id"] for x in c.get(f"{V1}/catalogue/components").json()["components"]}
    assert {"C1", "CO2", "H2O"} <= ids
    thermo = {x["id"]: x for x in c.get(f"{V1}/catalogue/thermo").json()["thermo"]}
    assert thermo["pr"]["registered"] is True


# --- projects -------------------------------------------------------------------------------------


def test_projects_crud() -> None:
    pid = _create("alpha")
    assert pid in {p["id"] for p in c.get(f"{V1}/projects").json()["projects"]}
    assert c.get(f"{V1}/projects/{pid}").json()["name"] == "alpha"
    _err(c.get(f"{V1}/projects/nope"), 404, "unknown_project")
    _err(c.post(f"{V1}/projects", json={"name": "alpha"}), 409, "duplicate_name")
    _err(c.post(f"{V1}/projects", json={"name": "x", "template": "nope"}), 422, "invalid")
    _err(c.post(f"{V1}/projects", json={"name": ""}), 422, "validation_error")
    assert c.patch(f"{V1}/projects/{pid}", json={"name": "beta"}).json()["name"] == "beta"
    fs = c.get(f"{V1}/projects/{pid}/flowsheet").json()
    assert "V-101" in {u["tag"] for u in fs["units"]}
    assert c.delete(f"{V1}/projects/{pid}").json() == {"deleted": True}
    _err(c.delete(f"{V1}/projects/{pid}"), 404, "unknown_project")


# --- thermo / components ---------------------------------------------------------------------------


def test_thermo_and_components(pid: str) -> None:
    assert c.get(f"{V1}/projects/{pid}/thermo").json()["package"] == "pr"
    r = c.put(f"{V1}/projects/{pid}/thermo", json={"package": "srk"})
    assert r.status_code == 200 and r.json()["change"]["diff"]["thermo"] == {"from": "pr", "to": "srk"}
    _err(c.put(f"{V1}/projects/{pid}/thermo", json={"package": "magic"}), 422, "unknown_thermo")
    recs = c.get(f"{V1}/projects/{pid}/thermo/recommend").json()
    assert recs["recommendations"]
    slate = c.get(f"{V1}/projects/{pid}/thermo").json()["components"]
    assert c.put(f"{V1}/projects/{pid}/components", json={"components": slate}).status_code == 200
    _err(c.put(f"{V1}/projects/{pid}/components", json={"components": ["C1"]}), 422, "invalid_project")


# --- units --------------------------------------------------------------------------------------------


def test_units(pid: str) -> None:
    base = f"{V1}/projects/{pid}/units"
    assert "K-101" in {u["tag"] for u in c.get(base).json()["units"]}
    r = c.post(base, json={"kind": "cooler", "tag": "E-201", "params": {"dP": 0}, "grid": {"q": 2, "r": 0}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["result"]["added"] == "E-201" and body["change"]["op"] == "place_unit"
    assert body["change"]["actor"] == "api"
    assert body["result"]["position"]["x"] == pytest.approx(120.0)
    _err(c.post(base, json={"kind": "cooler", "tag": "E-201"}), 409, "duplicate_tag")
    _err(c.post(base, json={"kind": "warp"}), 422, "unknown_kind")
    _err(
        c.post(base, json={"kind": "cooler", "position": {"x": 1, "y": 1}, "grid": {"q": 0, "r": 0}}),
        422,
        "bad_position",
    )
    assert c.get(f"{base}/E-201").json()["position"]["pfd"]["x"] == pytest.approx(120.0)
    _err(c.get(f"{base}/E-999"), 404, "unknown_unit")
    r = c.patch(f"{base}/E-201", json={"params": {"T_out": 300.0}}, headers={"X-Stomato-Actor": "ui"})
    assert r.json()["result"]["params"] == {"dP": 0, "T_out": 300.0} and r.json()["change"]["actor"] == "ui"
    _err(
        c.patch(f"{base}/E-201", json={"params": {}}, headers={"X-Stomato-Actor": "bad actor!"}),
        400,
        "bad_actor",
    )
    r = c.put(f"{base}/E-201/position", json={"view": "pid", "position": {"x": 5, "y": 6}})
    assert r.json()["result"] == {"tag": "E-201", "view": "pid", "x": 5.0, "y": 6.0}
    _err(c.put(f"{base}/E-201/position", json={"view": "pid"}), 422, "bad_position")
    assert c.delete(f"{base}/E-201").json()["result"]["removed"] == "E-201"
    _err(c.delete(f"{base}/E-201"), 404, "unknown_unit")


# --- streams ------------------------------------------------------------------------------------------


def test_streams(pid: str) -> None:
    base = f"{V1}/projects/{pid}/streams"
    assert len(c.get(base).json()["streams"]) == 11
    c.post(f"{V1}/projects/{pid}/units", json={"kind": "cooler", "tag": "E-201"})
    feed = {"T": 300.0, "P": 2e6, "molar_flow": 10.0, "composition": {"C1": 0.9, "C2": 0.1}}
    r = c.post(base, json={"id": "S-050", "target": {"unit": "E-201", "port": "inlet"}, "feed": feed})
    assert r.status_code == 201, r.text
    assert r.json()["change"]["diff"]["streams"]["added"][0]["id"] == "S-050"
    r = c.post(base, json={"source": {"unit": "E-201", "port": "outlet"}})
    assert r.status_code == 201 and r.json()["result"]["to"] == "product (battery limit)"
    _err(c.post(base, json={"target": {"unit": "E-201", "port": "inlet"}}), 422, "invalid_project")
    _err(
        c.post(base, json={"id": "S-051", "target": {"unit": "E-201", "port": "nope"}, "feed": feed}),
        422,
        "bad_port",
    )
    assert c.get(f"{base}/S-050").json()["feed"]["T"] == 300.0
    _err(c.get(f"{base}/S-999"), 404, "unknown_stream")
    r = c.patch(f"{base}/S-050", json={"service": "PG", "feed": {"T": 310.0}})
    assert r.json()["result"]["stream"]["feed"]["T"] == 310.0
    _err(c.patch(f"{base}/S-002", json={"feed": {"T": 310.0}}), 422, "not_a_feed")
    _err(c.patch(f"{base}/S-050", json={}), 422, "nothing_to_change")
    assert c.delete(f"{base}/S-050").json()["result"] == {"disconnected": "S-050"}
    _err(c.delete(f"{base}/S-050"), 404, "unknown_stream")


# --- cells and design specs ---------------------------------------------------------------------------


def test_cells(pid: str) -> None:
    base = f"{V1}/projects/{pid}/cells"
    cells = {x["address"]: x for x in c.get(base).json()["cells"]}
    assert cells["K-101.params.P_out"]["unit"] == "Pa"
    assert c.get(f"{base}/S-001.feed.T").json()["unit"] == "K"
    _err(c.get(f"{base}/S-002.feed.T"), 404, "unknown_address")
    r = c.put(f"{base}/S-001.feed.T", json={"value": 30, "unit": "degC"})
    assert r.json()["result"]["value"] == pytest.approx(303.15)
    assert r.json()["change"]["lines"] == ["~ S-001.feed.T: 293.15 -> 303.15"]
    _err(c.put(f"{base}/S-001.feed.T", json={"value": 30, "unit": "bar"}), 422, "unit_mismatch")
    _err(c.put(f"{base}/S-001.feed.T", json={"value": "hot"}), 422, "invalid_value")


def test_design_specs(pid: str) -> None:
    base = f"{V1}/projects/{pid}/design-specs"
    spec = {
        "id": "DS-1",
        "target": "S-003.T",
        "value": 400.0,
        "manipulated": "K-101.params.P_out",
        "lower": 5e6,
        "upper": 8e6,
    }
    r = c.post(base, json=spec)
    assert r.status_code == 201 and r.json()["result"]["added"] == "DS-1"
    assert [s["id"] for s in c.get(base).json()["design_specs"]] == ["DS-1"]
    _err(c.post(base, json=spec), 409, "duplicate_id")
    _err(c.post(base, json={**spec, "id": "DS-2", "lower": 9e6}), 422, "invalid_project")
    assert c.delete(f"{base}/DS-1").json()["result"] == {"removed": "DS-1"}
    _err(c.delete(f"{base}/DS-1"), 404, "unknown_design_spec")


# --- solve, results, provenance, exports -----------------------------------------------------------------


def test_solve_results_and_values(pid: str) -> None:
    solved = c.post(f"{V1}/projects/{pid}/solve").json()
    assert solved["converged"] is True and solved["status"] == "converged"
    assert c.get(f"{V1}/projects/{pid}/results").json()["streams"]["S-003"]["T"] > 0
    assert c.get(f"{V1}/projects/{pid}/results/streams/S-003").json()["state"]["T"] > 0
    _err(c.get(f"{V1}/projects/{pid}/results/streams/S-999"), 404, "unknown_stream")
    assert "outlets" in c.get(f"{V1}/projects/{pid}/results/units/K-101").json()
    _err(c.get(f"{V1}/projects/{pid}/results/units/K-999"), 404, "unknown_unit")
    v = c.get(f"{V1}/projects/{pid}/results/values/K-101.power_W", params={"unit": "kW"}).json()
    assert v["unit"] == "kW" and v["value"] == pytest.approx(v["si_value"] / 1000)
    _err(c.get(f"{V1}/projects/{pid}/results/values/K-101.nope"), 404, "unknown_address")


def test_solve_with_missing_plugin_is_501() -> None:
    pid = _create("broken")
    project = c.get(f"{V1}/projects/{pid}/exports/project.json").json()
    project["flowsheet"]["units"][0]["kind"] = "no_such_kind"
    assert c.put(f"/api/projects/{pid}", json=project).status_code == 200
    _err(c.post(f"{V1}/projects/{pid}/solve"), 501, "unknown_plugin")


def test_solve_job(pid: str) -> None:
    r = c.post(f"{V1}/projects/{pid}/solve/jobs")
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert run_worker(routes_jobs._job_queue(), once=True) == 1
    assert c.get(f"{V1}/jobs/{job_id}").json()["status"] == "done"
    frames = [
        json.loads(line[6:])
        for line in c.get(f"{V1}/jobs/{job_id}/events").text.splitlines()
        if line.startswith("data: ")
    ]
    assert frames[-1]["type"] == "done"
    _err(c.get(f"{V1}/jobs/nope"), 404, "not_found")
    _err(c.get(f"{V1}/jobs/nope/events"), 404, "not_found")


def test_trace_explain_audit(pid: str) -> None:
    sub = c.get(f"{V1}/projects/{pid}/trace", params={"address": "S-003.T"}).json()
    assert sub["values"] and sub["meta"]["focus"]
    full = c.get(f"{V1}/projects/{pid}/trace").json()
    assert len(full["values"]) > len(sub["values"])
    explained = c.get(f"{V1}/projects/{pid}/trace/explain", params={"address": "S-003.T"}).json()
    assert explained["steps"] and explained["text"]
    _err(c.get(f"{V1}/projects/{pid}/trace/explain", params={"address": "S-003.zzz"}), 404, "not_traced")
    _err(c.get(f"{V1}/projects/{pid}/trace/explain"), 422, "validation_error")
    assert "outputs" in c.get(f"{V1}/projects/{pid}/trace/audit").json()


def test_exports(pid: str) -> None:
    assert c.get(f"{V1}/projects/{pid}/exports/project.json").json()["flowsheet"]["units"]
    csv = c.get(f"{V1}/projects/{pid}/exports/sheet.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert c.get(f"{V1}/projects/{pid}/exports/sheet.html").headers["content-type"].startswith("text/html")
    _err(c.get(f"{V1}/projects/{pid}/exports/sheet.pdf"), 422, "validation_error")
    for view in ("pfd", "pid"):
        r = c.get(f"{V1}/projects/{pid}/exports/{view}.svg")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


# --- history ---------------------------------------------------------------------------------------------


def test_history_undo_redo_and_stream(pid: str) -> None:
    _err(c.post(f"{V1}/projects/{pid}/undo"), 409, "nothing_to_undo")
    c.post(f"{V1}/projects/{pid}/units", json={"kind": "cooler", "tag": "E-201"})
    c.put(f"{V1}/projects/{pid}/cells/E-101.params.dP", json={"value": 0.2, "unit": "bar"})
    log = c.get(f"{V1}/projects/{pid}/changes").json()["changes"]
    assert [x["op"] for x in log] == ["place_unit", "set_cell"]
    assert c.get(f"{V1}/projects/{pid}/changes", params={"after": 1}).json()["changes"][0]["seq"] == 2
    _err(c.get(f"{V1}/projects/{pid}/changes", params={"limit": 0}), 422, "validation_error")
    undone = c.post(f"{V1}/projects/{pid}/undo").json()
    assert undone["result"]["undo"] == 2 and undone["change"]["kind"] == "undo"
    assert undone["change"]["diff"]["units"]["changed"][0]["tag"] == "E-101"
    assert c.post(f"{V1}/projects/{pid}/redo").json()["result"]["redo"] == 2
    _err(c.post(f"{V1}/projects/{pid}/redo"), 409, "nothing_to_redo")
    text = c.get(f"{V1}/projects/{pid}/changes/stream", params={"follow": False, "after": 1}).text
    frames = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert [f["change"]["seq"] for f in frames] == [2, 3, 4]
    assert all(f["type"] == "change" for f in frames)
    assert "id: 4" in text


def test_legacy_put_is_undoable(pid: str) -> None:
    project = c.get(f"{V1}/projects/{pid}/exports/project.json").json()
    project["flowsheet"]["thermo"] = "srk"
    c.put(f"/api/projects/{pid}", json=project)
    assert c.get(f"{V1}/projects/{pid}/changes").json()["changes"][0]["op"] == "put"
    c.post(f"{V1}/projects/{pid}/undo")
    assert c.get(f"{V1}/projects/{pid}/thermo").json()["package"] == "pr"


# --- tools and agent ---------------------------------------------------------------------------------------


def test_tool_runner(pid: str) -> None:
    r = c.post(
        f"{V1}/projects/{pid}/tools/place_unit",
        json={"kind": "cooler", "tag": None, "params": None, "position": None, "grid": None, "view": None},
        headers={"X-Stomato-Actor": "script"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["change"]["actor"] == "script"
    read = c.post(f"{V1}/projects/{pid}/tools/read_results", json={"address": "S-001.T", "unit": "degC"})
    assert read.json()["change"] is None and read.json()["result"]["unit"] == "degC"
    _err(c.post(f"{V1}/projects/{pid}/tools/nope", json={}), 404, "unknown_tool")
    _err(
        c.post(
            f"{V1}/projects/{pid}/tools/move_unit",
            json={"tag": "X-1", "position": None, "grid": {"q": 0, "r": 0}, "view": None},
        ),
        422,
        "unknown_unit",
    )


def test_agent_scripted(pid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOMATO_AGENT_MODE", "scripted")
    text = c.post(f"{V1}/projects/{pid}/agent", json={"message": "solve it"}).text
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "done"
    assert events[-1]["conversation_id"] in c.get(f"{V1}/projects/{pid}/agent").json()["conversations"]
    _err(c.post(f"{V1}/projects/{pid}/agent", json={"message": "  "}), 422, "invalid")


def test_foreign_owner_is_403_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from ngdesign.api import auth

    monkeypatch.setenv("STOMATO_API_TOKENS", "ta:alice,tb:bob")
    auth.reset_auth_cache()
    r = c.post(f"{V1}/projects", json={"name": "a"}, headers={"Authorization": "Bearer ta"})
    assert r.status_code == 201
    _err(c.get(f"{V1}/projects/{r.json()['id']}", headers={"Authorization": "Bearer tb"}), 403, "forbidden")
    _err(c.get(f"{V1}/projects"), 401, "unauthorized")


# --- the OpenAPI document ------------------------------------------------------------------------------


def test_openapi_documents_v1_with_examples_and_envelope() -> None:
    schema = app.openapi()
    v1_paths = [p for p in schema["paths"] if p.startswith(V1)]
    assert len(v1_paths) >= 30
    for path in v1_paths:
        for op in schema["paths"][path].values():
            assert op.get("tags"), path
            assert "422" in op["responses"] or "404" in op["responses"], path
    for name in ("UnitCreate", "CellSet", "StreamCreate", "DesignSpecIn", "ThermoSet"):
        assert schema["components"]["schemas"][name].get("examples"), name
    assert "ErrorEnvelope" in schema["components"]["schemas"]


def test_change_stream_defaults_to_live_and_actor_binds_legacy_writes(pid: str) -> None:
    c.post(f"{V1}/projects/{pid}/units", json={"kind": "cooler", "tag": "E-201"})
    # No `after`: only changes newer than the latest one at connect time.
    text = c.get(f"{V1}/projects/{pid}/changes/stream", params={"follow": False}).text
    assert "data: " not in text
    # A legacy write carries the caller's X-Stomato-Actor into the log.
    project = c.get(f"{V1}/projects/{pid}/exports/project.json").json()
    project["flowsheet"]["thermo"] = "srk"
    c.put(f"/api/projects/{pid}", json=project, headers={"X-Stomato-Actor": "ui:tab-1"})
    last = c.get(f"{V1}/projects/{pid}/changes", params={"after": 1}).json()["changes"][0]
    assert last["op"] == "put" and last["actor"] == "ui:tab-1"
    r = c.put(f"/api/projects/{pid}", json=project, headers={"X-Stomato-Actor": "no spaces"})
    assert r.status_code == 400 and r.json() == {
        "detail": "X-Stomato-Actor must be 1-64 chars of letters, digits and :_.-"
    }
