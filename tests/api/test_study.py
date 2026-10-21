"""P2-04 acceptance: POST /api/study runs the grid on the current project."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ngdesign.api.app import app

c = TestClient(app)


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _body(inputs: list[dict[str, object]], outputs: list[str]) -> dict[str, object]:
    return {"id": "study", "inputs": inputs, "outputs": outputs}


def test_study_returns_rows_over_the_current_project() -> None:
    _reset()
    r = c.post(
        "/api/study",
        json=_body(
            [{"address": "K-101.params.P_out", "values": [7.0e6, 8.0e6, 9.0e6]}],
            ["K-101.power_W"],
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 3
    assert body["failed"] == []
    assert [row["status"] for row in body["rows"]] == ["converged"] * 3
    powers = [row["outputs"]["K-101.power_W"] for row in body["rows"]]
    assert all(b > a for a, b in zip(powers, powers[1:], strict=False))


def test_study_failed_case_is_a_row_not_an_error() -> None:
    _reset()
    r = c.post(
        "/api/study",
        json=_body(
            [{"address": "K-101.params.P_out", "values": [-1.0, 8.0e6]}],
            ["K-101.power_W"],
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 2
    failed = [row for row in body["rows"] if row["status"] == "failed"]
    assert len(failed) == 1 and len(body["failed"]) == 1
    assert failed[0]["errors"], "the failed row carries its UnitErrors"


def test_study_unknown_write_address_is_data_not_4xx() -> None:
    _reset()
    r = c.post(
        "/api/study",
        json=_body([{"address": "X-999.params.P_out", "values": [8.0e6]}], ["K-101.power_W"]),
    )
    assert r.status_code == 200
    row = r.json()["rows"][0]
    assert row["status"] == "failed" and row["message"] is not None


def test_study_empty_grid_is_422() -> None:
    _reset()
    r = c.post("/api/study", json=_body([], ["K-101.power_W"]))
    # A CaseStudy without any axis is structurally impossible: pydantic cannot
    # see it, so run() raises and the route maps it to 422.
    assert r.status_code == 422
    r = c.post(
        "/api/study",
        json=_body([{"address": "K-101.params.P_out", "values": []}], ["K-101.power_W"]),
    )
    assert r.status_code == 422 and "no values" in r.json()["detail"]


def test_study_missing_thermo_plugin_is_501() -> None:
    """The registry KeyError for an unregistered thermo name surfaces as 501,
    the same contract POST /api/solve holds for a missing unit plugin."""
    _reset()
    project = c.get("/api/project").json()
    project["flowsheet"]["thermo"] = "no_such_thermo"
    assert c.put("/api/project", json=project).status_code == 200
    r = c.post(
        "/api/study",
        json=_body([{"address": "K-101.params.P_out", "values": [8.0e6]}], ["K-101.power_W"]),
    )
    assert r.status_code == 501 and "no_such_thermo" in r.json()["detail"]
