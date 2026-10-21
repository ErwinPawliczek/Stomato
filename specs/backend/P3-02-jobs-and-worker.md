# P3-02: Solve jobs — queue, worker process, progress stream

- **Phase:** 3
- **Depends on:** P3-01 (store), P2-02 (history records)
- **Packages you may edit:** `ngdesign.jobs` (new), `ngdesign.api` (`routes_jobs.py`, `app.py` include), `ngdesign.cli` (`worker` command), `tests/jobs/`, `tests/api/test_jobs.py`, `pyproject.toml` + `uv.lock` **only to add `redis`**, `openapi.json` + `schema.d.ts` (regenerated)
- **Contract change:** yes — new routes, dependency
- **Benchmark delta expected:** none

## Goal
A 10-minute column solve must not block an API worker, and Phase 3's gate wants a solve that shows
progress. Solves become jobs: the API enqueues, a worker process solves, progress streams back.

## Files
- Create `src/ngdesign/jobs/` — `queue.py` (`JobQueue` protocol: `enqueue(job) -> id`, `claim()`,
  `complete(id, result)`, `fail(id, error)`, `progress(id, record)`; `RedisQueue` on
  `STOMATO_REDIS_URL`, `LocalQueue` (thread-backed, same process) when unset — tests use the local one,
  one Redis test runs when `STOMATO_TEST_REDIS_URL` is set), `worker.py` (`run_worker(queue, store)`:
  claim → `agent.engine.solve_project` with a progress callback that forwards each P2-02 `TearRecord`
  → store `SolveRow` → complete), `models.py` (`Job(id, kind="solve", project_id, project_hash,
  status: queued|running|done|failed, created_at, started_at, finished_at, error, progress:
  list[TearRecord])`).
- Edit `solver/sequential_modular.py` only to accept an optional `on_progress` callback (P2-02 records)
  — no numeric change.
- API: `POST /api/projects/{id}/jobs/solve` → `{job_id}` (202); `GET /api/jobs/{job_id}` → `Job`;
  `GET /api/jobs/{job_id}/events` → SSE of progress records then `done|failed`; `POST /api/solve` (and
  the scoped twin) keep returning synchronously but go through the same engine path.
- CLI: `ngdesign worker` runs `run_worker` until SIGTERM; `--once` for tests.
- Tests: local queue end to end (enqueue → worker thread → result row → SSE events in order);
  failed solve → `failed` with the P2-02 errors; two workers on one queue claim distinct jobs.

## Acceptance criteria
- [ ] All tests above PASS; existing tests unchanged; `openapi.json`/`schema.d.ts` regenerated; frontend gates green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
