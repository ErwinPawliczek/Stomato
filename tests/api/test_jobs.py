"""Spec P3-02 API acceptance: jobs enqueue 202, GET, and SSE events in order.

Uses the default LocalQueue (``STOMATO_REDIS_URL`` unset); the worker runs via
``run_worker(once=True)`` or a thread, exactly what ``ngdesign worker --once``
runs. The synchronous ``POST /api/solve`` surface is unchanged (locked tests in
``test_solve.py`` keep guarding it); these tests cover the async twin.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api import routes_jobs
from ngdesign.api.app import app
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, Project, StreamSpec, UnitSpec
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.jobs.worker import run_worker

c = TestClient(app)

BOOM_KIND = "p3_api_boom"
BOOM_MESSAGE = "boom: api-level failure"


class _Boom:
    """A plugin bug on the job path: raises instead of returning outlets."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out",)

    def solve(self, inlets: Any, params: Any, thermo: Any) -> Any:
        raise RuntimeError(BOOM_MESSAGE)


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    """Fresh engine cache per test (progress records must be produced, not
    replayed from the project-hash cache); no Redis backend."""
    from ngdesign.agent import engine

    engine._cache.clear()
    yield
    engine._cache.clear()


def _create_project(name: str, project: Project | None = None) -> str:
    body = project or Project(name="slice", flowsheet=slice_fs.build())
    r = c.post("/api/projects", json={"name": name, "project": body.model_dump()})
    assert r.status_code == 201, r.text
    id_ = r.json()["id"]
    assert isinstance(id_, str)
    return id_


def _boom_project(name: str) -> Project:
    flowsheet = Flowsheet(
        name=name,
        units=[UnitSpec(tag="B-101", kind=BOOM_KIND)],
        streams=[
            StreamSpec(
                id="F-001",
                target=PortRef(unit="B-101", port="inlet"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=100.0, composition={"C1": 1.0}),
            ),
            StreamSpec(id="P-002", source=PortRef(unit="B-101", port="out")),
        ],
    )
    return Project(name=name, flowsheet=flowsheet)


def _drain_events(job_id: str) -> list[dict[str, Any]]:
    """Read the SSE stream to its end; return the decoded data payloads."""
    frames: list[dict[str, Any]] = []
    with c.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                frames.append(json.loads(line[len("data: ") :]))
    return frames


def test_enqueue_poll_stream_done() -> None:
    """202 with a job id → queued → worker → done; SSE yields progress frames
    then exactly one done frame, in order."""
    project_id = _create_project("jobs-demo")
    r = c.post(f"/api/projects/{project_id}/jobs/solve")
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    body = c.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "queued"
    assert body["kind"] == "solve"
    assert body["project_id"] == project_id
    assert body["error"] is None

    assert run_worker(routes_jobs._job_queue(), once=True) == 1

    body = c.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["started_at"] is not None and body["finished_at"] is not None

    events = _drain_events(job_id)
    types = [event["type"] for event in events]
    assert types[-1] == "done"
    assert types.count("done") == 1
    assert all(t in ("progress", "done") for t in types)
    iterations = [event["record"]["iteration"] for event in events if event["type"] == "progress"]
    assert iterations == sorted(iterations)
    assert events[-1]["job_id"] == job_id


def test_stream_live_while_worker_runs() -> None:
    """Streaming while the worker solves: every progress frame in solve order,
    exactly one terminal frame at the very end."""
    project_id = _create_project("jobs-live")
    job_id = c.post(f"/api/projects/{project_id}/jobs/solve").json()["job_id"]
    stop = threading.Event()
    worker = threading.Thread(
        target=run_worker,
        args=(routes_jobs._job_queue(),),
        kwargs={"stop_event": stop},
        daemon=True,
    )
    worker.start()
    try:
        events = _drain_events(job_id)
    finally:
        stop.set()
        worker.join(5)
    types = [event["type"] for event in events]
    assert types[-1] == "done"
    assert types.count("done") == 1
    iterations = [event["record"]["iteration"] for event in events if event["type"] == "progress"]
    assert iterations == sorted(iterations)


def test_failed_job_streams_failed_with_errors() -> None:
    """A solve whose partial sheet is failed: job failed, SSE ends failed with
    the P2-02 UnitError message."""
    registry.register("unit", BOOM_KIND)(_Boom)
    try:
        project_id = _create_project("jobs-boom", _boom_project("jobs-boom"))
        job_id = c.post(f"/api/projects/{project_id}/jobs/solve").json()["job_id"]
        assert run_worker(routes_jobs._job_queue(), once=True) == 1
        body = c.get(f"/api/jobs/{job_id}").json()
        assert body["status"] == "failed"
        assert BOOM_MESSAGE in body["error"]
        events = _drain_events(job_id)
        assert events[-1]["type"] == "failed"
        assert BOOM_MESSAGE in events[-1]["error"]
        assert all(event["type"] in ("progress", "failed") for event in events)
        assert [event["type"] for event in events].count("failed") == 1
    finally:
        registry._REGISTRY["unit"].pop(BOOM_KIND, None)  # no public unregister


def test_unknown_job_404() -> None:
    assert c.get("/api/jobs/does-not-exist").status_code == 404
    assert c.get("/api/jobs/does-not-exist/events").status_code == 404


def test_enqueue_unknown_project_404() -> None:
    assert c.post("/api/projects/does-not-exist/jobs/solve").status_code == 404


def test_synchronous_solve_unchanged() -> None:
    """POST /api/solve (and its scoped twin) keep returning synchronously with
    the full SolvedFlowsheet — the job routes add an async path, they do not
    replace the sync one (spec P3-02)."""
    assert c.post("/api/project/reset").status_code == 200
    r = c.post("/api/solve")
    assert r.status_code == 200
    assert r.json()["converged"] is True
    project = _create_project("jobs-sync")
    r = c.post(f"/api/projects/{project}/solve")
    assert r.status_code == 200
    assert r.json()["converged"] is True
