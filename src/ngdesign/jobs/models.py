"""The Job record (spec P3-02): one queued solve, its status and its progress.

Pure data over the contract models: ``progress`` holds the solver's P2-02
:class:`TearRecord` list verbatim, streamed to the client through the SSE
events route. The solved result itself is not carried on the Job — the worker
persists it as a store ``SolveRow`` (spec P3-01) keyed by the job id, so the
heavy payload is not duplicated into the queue backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ngdesign.contracts.common import Model
from ngdesign.contracts.diagnostics import TearRecord

#: Job lifecycle: queued (enqueued), running (claimed by a worker), done
#: (solved and persisted) or failed (the solve raised, or the solver returned
#: a partial sheet whose status is "failed" — ``error`` says why).
JobStatus = Literal["queued", "running", "done", "failed"]

#: What a job does. Only "solve" exists today; the field keeps the queue
#: forward-compatible with future job kinds without a schema change.
JobKind = Literal["solve"]


class Job(Model):
    """One solve job: identity, project binding, lifecycle, progress."""

    id: str  # uuid4().hex, assigned by the enqueue route
    kind: JobKind = "solve"
    project_id: str  # the store project the solve runs on
    project_hash: str  # the project hash at enqueue time (agent.engine.project_hash)
    status: JobStatus = "queued"
    created_at: datetime | None = None  # stamped by the queue on enqueue
    started_at: datetime | None = None  # stamped on claim
    finished_at: datetime | None = None  # stamped on complete/fail
    error: str | None = None  # the failure reason when status == "failed"
    progress: list[TearRecord] = Field(default_factory=list)  # P2-02 records, in append order
