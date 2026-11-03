"""GET /api/projects/{id}/trace and /trace/audit (docs/provenance.md section 6)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def _create(name: str) -> str:
    project: dict[str, Any] = c.get("/api/project").json()
    project["name"] = name
    response = c.post("/api/projects", json={"name": name, "project": project})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_trace_graph_subgraph_and_audit() -> None:
    pid = _create("traced")

    full = c.get(f"/api/projects/{pid}/trace")
    assert full.status_code == 200, full.text
    graph = full.json()
    assert graph["values"] and graph["ops"] and graph["edges"]
    outputs = [v for v in graph["values"] if v["kind"] == "output" and v["stream"]]
    assert outputs

    target = outputs[0]
    focused = c.get(f"/api/projects/{pid}/trace", params={"stream": target["stream"], "prop": target["prop"]})
    assert focused.status_code == 200, focused.text
    sub = focused.json()
    assert sub["meta"]["focus"] == target["id"]
    assert len(sub["values"]) < len(graph["values"])
    ids = {v["id"] for v in sub["values"]} | {o["id"] for o in sub["ops"]}
    assert all(e["source"] in ids and e["target"] in ids for e in sub["edges"])

    unit_value = next(v for v in graph["values"] if v["kind"] == "output" and not v["stream"])
    by_unit = c.get(
        f"/api/projects/{pid}/trace", params={"unit": unit_value["unit_tag"], "prop": unit_value["prop"]}
    )
    assert by_unit.status_code == 200

    report = c.get(f"/api/projects/{pid}/trace/audit")
    assert report.status_code == 200
    body = report.json()
    assert body["outputs"] == len([v for v in graph["values"] if v["kind"] == "output"])
    assert body["clean"] + len(body["findings"]) == body["outputs"]


def test_trace_query_errors() -> None:
    pid = _create("traced-errors")
    assert c.get(f"/api/projects/{pid}/trace", params={"stream": "S-001"}).status_code == 422
    assert c.get(f"/api/projects/{pid}/trace", params={"stream": "S-999", "prop": "T"}).status_code == 404
    assert c.get("/api/projects/nope/trace").status_code == 404
