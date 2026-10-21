"""The solve-job worker (spec P3-02): claim → solve (one path) → persist → settle.

:func:`run_worker` loops over a :class:`~ngdesign.jobs.queue.JobQueue`: claim a
job, solve its project through ``ngdesign.agent.engine.solve_project`` — the
one solve path with one cache (spec B-08) — forwarding every P2-02
:class:`TearRecord` the solver appends back into the queue as progress, persist
the result as a store ``SolveRow`` (spec P3-01, keyed by the job id), then
settle the job ``done`` or ``failed``. It runs until SIGTERM (``stop_event``)
or, with ``once=True``, processes at most one job — the CLI's ``--once`` test
seam.

Job outcome mapping: a solve that returns normally settles ``done`` — unless
the partial sheet's P2-02 status is ``"failed"`` (a unit failed outright), in
which case the job settles ``failed`` with the UnitError messages as its
``error``; the SolveRow is written either way, with the solver's own status. A
solve that raises (unknown plugin, invalid project) settles ``failed`` with the
exception message and writes no SolveRow.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ngdesign.agent import engine
from ngdesign.agent.tools import ProjectStore
from ngdesign.contracts import Project
from ngdesign.contracts.diagnostics import TearRecord
from ngdesign.contracts.flowsheet import SolvedFlowsheet
from ngdesign.jobs.models import Job
from ngdesign.jobs.queue import JobQueue
from ngdesign.store import DbProjectStore, ProjectNotFound, SolveRow, session
from ngdesign.store.models import utcnow

#: Seconds between claim attempts on an empty queue, and between state polls.
POLL_SECONDS = 0.2

#: The store a worker opens per job: one DbProjectStore per project id (jobs
#: from different projects share one worker, so the factory takes the id).
StoreFactory = Callable[[str], ProjectStore]

#: The ``chemicals`` databank lazy-loads its reaction/heat-capacity tables on
#: first use, and that lazy load is not thread-safe (two threads racing
#: ``_load_Cp_data`` crash with ``AttributeError: 'PiecewiseHeatCapacity'
#: object has no attribute 'append'``). Solve jobs are the one surface that
#: runs concurrent solves in a single process, so the worker resolves the
#: project's component slate once, serialized, before any solve — after that
#: the tables are loaded and concurrent solves are safe.
_databank_lock = threading.Lock()
_databank_warm = False


def _warm_databank(project: Project) -> None:
    """Resolve the project's component slate once per process, serialized.

    Resolution failures here are deliberately swallowed: the real solve
    re-resolves and reports them as proper engine errors with provenance.
    """
    global _databank_warm
    if _databank_warm:
        return
    with _databank_lock:
        if _databank_warm:
            return
        try:
            from ngdesign.contracts.components import resolve_set

            resolve_set(project.flowsheet.components)
        except Exception:
            pass
        finally:
            _databank_warm = True


def default_store_factory(project_id: str) -> DbProjectStore:
    """The production factory: the P3-01 store bound to the job's project."""
    return DbProjectStore(project_id)


def process_job(job: Job, queue: JobQueue, store_factory: StoreFactory) -> None:
    """Solve one claimed job end to end (see the module docstring for the
    outcome mapping). ``job`` must already be ``running`` (claimed)."""
    try:
        project = store_factory(job.project_id).get()
    except ProjectNotFound:
        queue.fail(job.id, f"project {job.project_id!r} no longer exists")
        return
    if engine.project_hash(project) != job.project_hash:
        # The project moved between enqueue and claim; the enqueued hash (and
        # with it the job's identity) is stale — fail instead of solving a
        # project the client did not enqueue.
        queue.fail(job.id, "project changed since the job was enqueued")
        return

    def on_progress(record: TearRecord) -> None:
        queue.progress(job.id, record)

    try:
        _warm_databank(project)
        solved: SolvedFlowsheet = engine.solve_project(project, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 — a job failure is data, never a crash
        queue.fail(job.id, f"{type(exc).__name__}: {exc}")
        return

    with session() as db:
        db.add(
            SolveRow(
                id=job.id,
                project_id=job.project_id,
                project_hash=job.project_hash,
                status=solved.status,
                result_json=solved.model_dump_json(),
                created_at=utcnow(),
            )
        )
    if solved.status == "failed":
        queue.fail(
            job.id,
            "; ".join(f"{error.tag} [{error.stage}]: {error.message}" for error in solved.errors),
        )
    else:
        queue.complete(job.id, solved)


def run_worker(
    queue: JobQueue,
    store_factory: StoreFactory = default_store_factory,
    *,
    once: bool = False,
    stop_event: threading.Event | None = None,
    poll_seconds: float = POLL_SECONDS,
) -> int:
    """Claim and process jobs until ``stop_event`` is set (SIGTERM via the CLI)
    or — ``once=True`` — one job has been processed, or none is queued.

    Returns the number of jobs processed. An empty queue sleeps
    ``poll_seconds`` and re-checks ``stop_event``, so a long-running worker
    stays responsive to SIGTERM while it waits for work.
    """
    processed = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            return processed
        job = queue.claim()
        if job is None:
            if once:
                return processed
            time.sleep(poll_seconds)
            continue
        process_job(job, queue, store_factory)
        processed += 1
        if once:
            return processed
