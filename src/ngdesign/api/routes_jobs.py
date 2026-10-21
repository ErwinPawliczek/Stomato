"""Solve-job routes (spec P3-02): enqueue, poll, stream progress as SSE.

``POST /api/projects/{id}/jobs/solve`` answers 202 with ``{job_id}`` — the
solve runs on a worker process, never the API worker. ``GET /api/jobs/{id}``
returns the :class:`~ngdesign.jobs.models.Job`; ``GET /api/jobs/{id}/events``
streams one SSE frame per P2-02 TearRecord as it lands, then a single
``done`` or ``failed`` frame, following ``api/routes_agent.py`` (B-08) for the
frame format and the ``StreamingResponse`` pattern. The frames generator polls
the queue backend, so both the LocalQueue (same process) and RedisQueue
(another process solved it) stream the same way.

Project scoping and auth reuse the P3-01 seams: the enqueue route takes the
``project_store`` dependency (404 unknown, 403 foreign owner); the job routes
resolve the job's own project through ``DbProjectStore`` and apply the same
owner check before answering. The synchronous ``POST /api/solve`` and its
scoped twin (routes_solve.py / routes_projects.py) are unchanged.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ngdesign.agent import engine
from ngdesign.api.auth import current_owner
from ngdesign.api.deps import project_store
from ngdesign.api.routes_agent import _sse  # the one SSE frame formatter (B-08)
from ngdesign.jobs.models import Job
from ngdesign.jobs.queue import JobQueue, queue_from_env
from ngdesign.store import DbProjectStore, ProjectNotFound
from ngdesign.store.models import utcnow

router = APIRouter()

#: The process-wide queue, built lazily from the environment (LocalQueue unless
#: STOMATO_REDIS_URL is set). Tests set this attribute directly.
_queue: JobQueue | None = None

#: Seconds between job-state polls in the SSE generator.
STREAM_POLL_SECONDS = 0.1


def _job_queue() -> JobQueue:
    """The process queue, built on first use from the environment."""
    global _queue
    if _queue is None:
        _queue = queue_from_env()
    return _queue


class JobEnqueued(BaseModel):
    """POST /api/projects/{id}/jobs/solve body (202)."""

    job_id: str


def _owned_job(job_id: str, owner: str) -> Job:
    """The job, after the same owner check ``project_store`` applies to
    project routes: 404 unknown job or deleted project, 403 foreign owner."""
    job = _job_queue().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    store = DbProjectStore(job.project_id)
    try:
        row = store.row()
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"unknown project {job.project_id!r}") from None
    if row.owner != owner:
        raise HTTPException(status_code=403, detail=f"job {job_id!r} belongs to another owner")
    return job


@router.post("/api/projects/{project_id}/jobs/solve", status_code=202)
def enqueue_solve_job(store: Annotated[DbProjectStore, Depends(project_store)]) -> JobEnqueued:
    """Enqueue a solve of the project; 202 with the job id — the worker solves
    it (a 10-minute column solve must not block an API worker)."""
    project = store.get()
    job = Job(
        id=uuid.uuid4().hex,
        project_id=store.project_id,
        project_hash=engine.project_hash(project),
        created_at=utcnow(),
    )
    _job_queue().enqueue(job)
    return JobEnqueued(job_id=job.id)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, owner: Annotated[str, Depends(current_owner)]) -> Job:
    """One job's identity, lifecycle and accumulated P2-02 progress records."""
    return _owned_job(job_id, owner)


def _job_frames(job_id: str) -> Iterator[str]:
    """SSE frames: one ``progress`` frame per queued TearRecord in solve order,
    then exactly one ``done`` or ``failed`` frame. Polls the queue backend so
    the stream works for jobs solved in this or another process."""
    sent = 0
    while True:
        job = _job_queue().get(job_id)
        if job is None:
            yield _sse({"type": "error", "message": f"unknown job {job_id!r}"})
            return
        for record in job.progress[sent:]:
            yield _sse({"type": "progress", "record": record.model_dump(mode="json")})
            sent += 1
        if job.status == "done":
            yield _sse({"type": "done", "job_id": job_id})
            return
        if job.status == "failed":
            yield _sse({"type": "failed", "job_id": job_id, "error": job.error})
            return
        time.sleep(STREAM_POLL_SECONDS)


@router.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, owner: Annotated[str, Depends(current_owner)]) -> StreamingResponse:
    """Stream the job's progress records, then done|failed, as SSE frames."""
    _owned_job(job_id, owner)  # 404/403 before the stream opens
    return StreamingResponse(
        _job_frames(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["enqueue_solve_job", "get_job", "job_events", "router"]
