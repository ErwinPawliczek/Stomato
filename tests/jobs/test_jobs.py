"""Spec P3-02 acceptance: LocalQueue end to end, failed solves, distinct claims.

The e2e test runs the real chain on a two-unit recycle loop (so the solver
produces P2-02 TearRecords): enqueue → worker thread → store SolveRow →
accumulated progress in solve order. The Redis test runs only against a real
Redis at ``STOMATO_TEST_REDIS_URL`` (CI never starts one).
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from sqlmodel import select

from ngdesign import registry
from ngdesign.agent.engine import project_hash
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, Project, SolvedFlowsheet, StreamSpec, UnitSpec
from ngdesign.contracts.diagnostics import TearRecord
from ngdesign.contracts.plugins import Thermo
from ngdesign.jobs.models import Job
from ngdesign.jobs.queue import TEST_REDIS_URL_ENV, LocalQueue, RedisQueue
from ngdesign.jobs.worker import run_worker
from ngdesign.store import DbProjectStore, SolveRow, create_project, session
from ngdesign.store.models import utcnow

#: Test-only pass-through and raising unit kinds, registered per test and
#: popped afterwards (the locked balance oracles never see them).
PASS_KIND = "p3_pass"
BOOM_KIND = "p3_boom"
MIX_KIND = "p3_mix"
BOOM_MESSAGE = "boom: two-phase inlet not accepted"

DEADLINE_S = 30.0


class _PassThrough:
    """Copies its single inlet to two outlets."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out", "vent")

    def solve(self, inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> Any:
        from ngdesign.contracts import UnitResult

        copied = inlets["inlet"].model_copy()
        return UnitResult(outlets={"out": copied, "vent": copied.model_copy()})


class _MixPass:
    """Copies inlet_a (the feed side) to both outlets; inlet_b (the recycle) is
    accepted and ignored, so the loop converges in a couple of Wegstein passes."""

    inlet_ports = ("inlet_a", "inlet_b")
    outlet_ports = ("out", "vent")

    def solve(self, inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> Any:
        from ngdesign.contracts import UnitResult

        copied = inlets["inlet_a"].model_copy()
        return UnitResult(outlets={"out": copied, "vent": copied.model_copy()})


class _Boom:
    """A plugin bug: raises instead of returning outlets."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out",)

    def solve(self, inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> Any:
        raise RuntimeError(BOOM_MESSAGE)


@pytest.fixture()
def _test_units() -> Iterator[None]:
    registry.register("unit", PASS_KIND)(_PassThrough)
    registry.register("unit", MIX_KIND)(_MixPass)
    registry.register("unit", BOOM_KIND)(_Boom)
    yield
    for name in (PASS_KIND, MIX_KIND, BOOM_KIND):
        registry._REGISTRY["unit"].pop(name, None)  # no public unregister


@pytest.fixture(autouse=True)
def _fresh_solve_cache() -> Iterator[None]:
    """Empty the engine's project-hash cache so every test actually solves
    (and produces progress records) instead of replaying a cached result."""
    from ngdesign.agent import engine

    engine._cache.clear()
    yield
    engine._cache.clear()


def _ring_flowsheet() -> Flowsheet:
    """F-001 -> M-101.inlet_a; M-101.out -> P-101.inlet; recycle P-101.out ->
    M-101.inlet_b (the torn stream); M-101.vent -> product. The pass-through
    loop converges in a few Wegstein passes, one TearRecord per pass."""
    return Flowsheet(
        name="ring",
        units=[UnitSpec(tag="M-101", kind=MIX_KIND), UnitSpec(tag="P-101", kind=PASS_KIND)],
        streams=[
            StreamSpec(
                id="F-001",
                target=PortRef(unit="M-101", port="inlet_a"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=100.0, composition={"C1": 1.0}),
            ),
            StreamSpec(
                id="S-002",
                source=PortRef(unit="M-101", port="out"),
                target=PortRef(unit="P-101", port="inlet"),
            ),
            StreamSpec(
                id="S-003",
                source=PortRef(unit="P-101", port="out"),
                target=PortRef(unit="M-101", port="inlet_b"),
            ),
            StreamSpec(id="P-004", source=PortRef(unit="M-101", port="vent")),
        ],
    )


def _boom_flowsheet() -> Flowsheet:
    """feed -> B-101 (raises) -> X-102 (would be an upstream skip)."""
    return Flowsheet(
        name="boom",
        units=[UnitSpec(tag="B-101", kind=BOOM_KIND), UnitSpec(tag="X-102", kind=PASS_KIND)],
        streams=[
            StreamSpec(
                id="F-001",
                target=PortRef(unit="B-101", port="inlet"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=100.0, composition={"C1": 1.0}),
            ),
            StreamSpec(
                id="S-002",
                source=PortRef(unit="B-101", port="out"),
                target=PortRef(unit="X-102", port="inlet"),
            ),
            StreamSpec(id="P-003", source=PortRef(unit="X-102", port="out")),
        ],
    )


def _enqueue(q: LocalQueue, flowsheet: Flowsheet) -> Job:
    """Store the project and enqueue its solve job on ``q``."""
    row = create_project(
        name=flowsheet.name, owner="local", project=Project(name=flowsheet.name, flowsheet=flowsheet)
    )
    job = Job(
        id=f"job-{row.id[:8]}",
        project_id=row.id,
        project_hash=project_hash(Project(name=flowsheet.name, flowsheet=flowsheet)),
    )
    q.enqueue(job)
    return job


def _wait_status(q: LocalQueue, job: Job, *statuses: str) -> Job:
    """Poll until the job reaches one of ``statuses``; fail loudly on timeout."""
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        current = q.get(job.id)
        assert current is not None
        if current.status in statuses:
            return current
        time.sleep(0.05)
    raise AssertionError(
        f"job {job.id} did not reach {statuses} within {DEADLINE_S}s (status {q.get(job.id)})"
    )


def _solve_row(job_id: str) -> SolveRow:
    with session() as db:
        row = db.exec(select(SolveRow).where(SolveRow.id == job_id)).first()
        assert row is not None, f"no SolveRow for job {job_id}"
        return row


def test_local_queue_end_to_end(_test_units: None) -> None:
    """enqueue → worker thread → result row → progress records in solve order."""
    q = LocalQueue()
    job = _enqueue(q, _ring_flowsheet())
    stop = threading.Event()
    worker = threading.Thread(target=run_worker, args=(q,), kwargs={"stop_event": stop}, daemon=True)
    worker.start()
    try:
        done = _wait_status(q, job, "done")
    finally:
        stop.set()
        worker.join(5)
    assert done.error is None
    assert done.started_at is not None and done.finished_at is not None
    # The result row: persisted through the P3-01 store, keyed by the job id.
    row = _solve_row(job.id)
    assert row.project_id == job.project_id
    assert row.status == "converged"
    assert SolvedFlowsheet.model_validate_json(row.result_json).converged is True
    # Progress: one TearRecord per tear stream per pass, in solve order.
    assert done.progress, "the recycle loop must produce tear-progress records"
    by_iteration = [r.iteration for r in done.progress]
    assert by_iteration == sorted(by_iteration)
    assert all(r.stream_id for r in done.progress)


def test_failed_solve_fails_job_with_p2_02_errors(_test_units: None) -> None:
    """A unit that raises: the partial sheet's status is failed, so the job
    settles failed with the P2-02 UnitError messages — and the SolveRow keeps
    the partial result."""
    q = LocalQueue()
    job = _enqueue(q, _boom_flowsheet())
    worker_count = run_worker(q, once=True)
    assert worker_count == 1
    failed = _wait_status(q, job, "failed")
    assert failed.error is not None and BOOM_MESSAGE in failed.error
    assert "B-101" in failed.error  # the failing unit's tag
    row = _solve_row(job.id)
    assert row.status == "failed"
    solved = SolvedFlowsheet.model_validate_json(row.result_json)
    assert solved.status == "failed"
    assert any(error.message == BOOM_MESSAGE for error in solved.errors)
    assert any(error.upstream for error in solved.errors)  # X-102 was skipped


def test_two_workers_claim_distinct_jobs(_test_units: None) -> None:
    """Two workers on one queue: each claims and processes a different job —
    a claimed job is marked running atomically, never solved twice."""
    q = LocalQueue()
    job_a = _enqueue(q, _ring_flowsheet())
    job_b = _enqueue(q, _boom_flowsheet())
    counts: dict[str, int] = {}

    def work(name: str) -> None:
        counts[name] = run_worker(q, once=True)

    threads = [threading.Thread(target=work, args=(name,)) for name in ("w1", "w2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert counts == {"w1": 1, "w2": 1}  # each worker processed exactly one job
    assert _wait_status(q, job_a, "done").status == "done"
    assert _wait_status(q, job_b, "failed").status == "failed"


def test_worker_once_with_empty_queue() -> None:
    """--once with nothing queued processes nothing and returns immediately."""
    assert run_worker(LocalQueue(), once=True) == 0


def test_job_gone_project_fails() -> None:
    """A job whose project row vanished fails with a reason, never crashes."""
    q = LocalQueue()
    job = Job(id="job-gone", project_id="does-not-exist", project_hash="0" * 64, created_at=utcnow())
    q.enqueue(job)
    run_worker(q, once=True)
    failed = _wait_status(q, job, "failed")
    assert "does-not-exist" in (failed.error or "")


def test_local_queue_progress_and_get_copy_safety() -> None:
    """progress appends in order; get returns an independent deep copy."""
    q = LocalQueue()
    job = Job(id="j1", project_id="p1", project_hash="0" * 64)
    assert q.enqueue(job) == "j1"
    record = TearRecord(
        iteration=1, stream_id="S-003", residual_max=0.5, residual_vector={"T": 0.5}, acceleration="direct"
    )
    q.progress("j1", record)
    got = q.get("j1")
    assert got is not None and [r.stream_id for r in got.progress] == ["S-003"]
    got.progress.append(record.model_copy(update={"iteration": 99}))  # mutate the copy
    again = q.get("j1")
    assert again is not None and len(again.progress) == 1  # the stored job is untouched
    assert q.get("unknown") is None
    assert q.claim() is not None
    assert q.claim() is None  # claimed: nothing queued


def test_redis_queue_roundtrip() -> None:
    """RedisQueue against a real Redis (only when STOMATO_TEST_REDIS_URL is
    set): enqueue → claim → progress → complete, and get() reads it back.
    Never started by CI (spec P3-02)."""
    url = os.environ.get(TEST_REDIS_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_REDIS_URL_ENV} not set")
    import redis  # the spec's added dependency

    q = RedisQueue(url)
    cleaner = redis.Redis.from_url(url, decode_responses=True)
    cleaner.delete("stomato:jobs:queue", "stomato:jobs:job:rj1")
    try:
        job = Job(id="rj1", project_id="p1", project_hash="0" * 64)
        assert q.enqueue(job) == "rj1"
        claimed = q.claim()
        assert claimed is not None and claimed.status == "running"
        assert q.claim() is None  # claimed: nothing queued for a second worker
        record = TearRecord(
            iteration=1,
            stream_id="S-003",
            residual_max=0.5,
            residual_vector={"T": 0.5},
            acceleration="direct",
        )
        q.progress("rj1", record)
        assert q.get("rj1") is not None and len(q.get("rj1").progress) == 1  # type: ignore[union-attr]
        q.complete(
            "rj1",
            SolvedFlowsheet(
                flowsheet=Flowsheet(name="f", units=[], streams=[]),
                streams={},
                units={},
                converged=True,
                iterations=1,
                errors=[],
                history=[],
            ),
        )
        done = q.get("rj1")
        assert done is not None and done.status == "done" and done.finished_at is not None
    finally:
        cleaner.delete("stomato:jobs:queue", "stomato:jobs:job:rj1")


def test_worker_persists_scoped_result_through_project_store(_test_units: None) -> None:
    """The worker reads the project through the same P3-01 seam the API uses
    (a DbProjectStore factory), so scoping and auth stay in one place."""
    q = LocalQueue()
    flowsheet = _ring_flowsheet()
    row = create_project(name="scoped", owner="local", project=Project(name="scoped", flowsheet=flowsheet))
    store = DbProjectStore(row.id)
    assert store.get().name == "scoped"  # the factory seam the worker uses
    job = Job(
        id="job-scoped",
        project_id=row.id,
        project_hash=project_hash(Project(name="scoped", flowsheet=flowsheet)),
    )
    q.enqueue(job)
    run_worker(q, once=True)
    assert _wait_status(q, job, "done").status == "done"
    assert _solve_row(job.id).project_id == row.id
