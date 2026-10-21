"""Job queues (spec P3-02): one protocol, two backends.

:class:`LocalQueue` is thread-backed and same-process — the default (and what
every test uses): ``STOMATO_REDIS_URL`` unset. :class:`RedisQueue` runs on
Redis so several API replicas and several workers share one queue; its tests
only run when ``STOMATO_TEST_REDIS_URL`` is set (CI does not start Redis).

Claim semantics both backends honour: FIFO by enqueue order, one claim per
queued job — a claimed job is marked ``running`` atomically, so two workers on
one queue never process the same job.
"""

from __future__ import annotations

import os
import threading
from typing import Protocol

from ngdesign.contracts.diagnostics import TearRecord
from ngdesign.contracts.flowsheet import SolvedFlowsheet
from ngdesign.jobs.models import Job
from ngdesign.store.models import utcnow

#: Selects :class:`RedisQueue` when set; unset means :class:`LocalQueue`.
REDIS_URL_ENV = "STOMATO_REDIS_URL"

#: Only used by tests: when set, a real Redis server backs the RedisQueue test.
TEST_REDIS_URL_ENV = "STOMATO_TEST_REDIS_URL"

#: Redis key prefix, namespaced so one Redis can serve several deployments.
_PREFIX = "stomato:jobs"

#: Redis list holding the ids of queued jobs, in FIFO order.
_QUEUE_KEY = f"{_PREFIX}:queue"

#: Redis key of one job's JSON, ``f"{_PREFIX}:job:{job_id}"``.
_JOB_KEY = f"{_PREFIX}:job:{{job_id}}"


class JobQueue(Protocol):
    """The one queue surface the API, the worker and the tests talk to.

    ``get`` is not in spec P3-02's method list; it is added (deviation noted in
    the PR) because the API's ``GET /api/jobs/{job_id}`` and SSE route must
    read a job's current state without claiming it — both backends serve that
    with the same call.
    """

    def enqueue(self, job: Job) -> str:
        """Add ``job`` (status ``queued``) and return its id."""
        ...

    def claim(self) -> Job | None:
        """Atomically mark the oldest queued job ``running`` and return it;
        ``None`` when nothing is queued."""
        ...

    def complete(self, job_id: str, result: SolvedFlowsheet) -> None:
        """Mark the job ``done`` (the worker has already persisted ``result``
        as a SolveRow; the backend may keep it for in-process consumers)."""
        ...

    def fail(self, job_id: str, error: str) -> None:
        """Mark the job ``failed`` with ``error`` as the reason."""
        ...

    def progress(self, job_id: str, record: TearRecord) -> None:
        """Append one P2-02 TearRecord to the job's progress, in solve order."""
        ...

    def get(self, job_id: str) -> Job | None:
        """The job's current state; ``None`` for an unknown id."""
        ...


class LocalQueue:
    """Thread-backed in-process queue: dicts under one lock.

    Instances are independent (each test builds its own); the API builds one
    module-level instance lazily. ``complete`` keeps the solved result in
    memory keyed by job id (:meth:`result`), same-process consumers only — the
    durable copy is the store's SolveRow.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []  # enqueue order; claim scans it FIFO
        self._results: dict[str, SolvedFlowsheet] = {}

    def enqueue(self, job: Job) -> str:
        with self._lock:
            if job.created_at is None:
                job.created_at = utcnow()
            self._jobs[job.id] = job
            self._order.append(job.id)
            return job.id

    def claim(self) -> Job | None:
        with self._lock:
            for job_id in self._order:
                job = self._jobs[job_id]
                if job.status == "queued":
                    job.status = "running"
                    job.started_at = utcnow()
                    return job.model_copy(deep=True)
            return None

    def complete(self, job_id: str, result: SolvedFlowsheet) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "done"
            job.finished_at = utcnow()
            job.error = None
            self._results[job_id] = result

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.finished_at = utcnow()
            job.error = error

    def progress(self, job_id: str, record: TearRecord) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.progress.append(record)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job is not None else None

    def result(self, job_id: str) -> SolvedFlowsheet | None:
        """The solved result kept by :meth:`complete` (same process only)."""
        with self._lock:
            return self._results.get(job_id)


class RedisQueue:
    """Redis-backed queue for several API replicas and workers sharing one list.

    Job state lives as JSON under ``stomato:jobs:job:{id}``; the queue itself
    is a Redis list of queued ids. ``claim`` pops atomically (``lpop``), so two
    workers never claim the same job. The redis package is imported lazily so
    the default (local) deployment never needs it loaded.
    """

    def __init__(self, url: str) -> None:
        import redis  # noqa: PLC0415 — lazy: only the Redis backend pays for it

        self._redis = redis.Redis.from_url(url, decode_responses=True)

    def _read(self, job_id: str) -> Job | None:
        raw = self._redis.get(_JOB_KEY.format(job_id=job_id))
        return Job.model_validate_json(raw) if raw is not None else None

    def _write(self, job: Job) -> None:
        self._redis.set(_JOB_KEY.format(job_id=job.id), job.model_dump_json())

    def enqueue(self, job: Job) -> str:
        if job.created_at is None:
            job.created_at = utcnow()
        pipe = self._redis.pipeline()
        pipe.set(_JOB_KEY.format(job_id=job.id), job.model_dump_json())
        pipe.rpush(_QUEUE_KEY, job.id)
        pipe.execute()
        return job.id

    def claim(self) -> Job | None:
        while True:
            popped = self._redis.lpop(_QUEUE_KEY)
            if popped is None:
                return None
            job = self._read(str(popped))
            if job is None:  # expired/lost job data: skip the stale id
                continue
            job.status = "running"
            job.started_at = utcnow()
            self._write(job)
            return job

    def complete(self, job_id: str, result: SolvedFlowsheet) -> None:
        job = self._read(job_id)
        if job is None:
            return
        job.status = "done"
        job.finished_at = utcnow()
        job.error = None
        self._write(job)

    def fail(self, job_id: str, error: str) -> None:
        job = self._read(job_id)
        if job is None:
            return
        job.status = "failed"
        job.finished_at = utcnow()
        job.error = error
        self._write(job)

    def progress(self, job_id: str, record: TearRecord) -> None:
        job = self._read(job_id)
        if job is None:
            return
        job.progress.append(record)
        self._write(job)

    def get(self, job_id: str) -> Job | None:
        return self._read(job_id)


def queue_from_env() -> JobQueue:
    """The configured backend: RedisQueue on ``STOMATO_REDIS_URL``, else the
    thread-backed LocalQueue (the default, and what every test uses)."""
    url = os.environ.get(REDIS_URL_ENV)
    return RedisQueue(url) if url else LocalQueue()


__all__ = ["REDIS_URL_ENV", "TEST_REDIS_URL_ENV", "JobQueue", "LocalQueue", "RedisQueue", "queue_from_env"]
