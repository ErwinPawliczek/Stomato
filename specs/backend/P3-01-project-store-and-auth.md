# P3-01: Project store (SQLModel), multi-project API, token auth, locked CORS

- **Phase:** 3
- **Depends on:** B-08 (`ProjectStore` seam, conversations), P2-02 (`SolvedFlowsheet.status`)
- **Packages you may edit:** `ngdesign.store` (new), `ngdesign.api`, `ngdesign.agent` (only `routes_agent`'s store/conversation wiring moves), `ngdesign.cli` (`serve`, `db` commands), `tests/store/`, `tests/api/`, `pyproject.toml` + `uv.lock` **only to add `sqlmodel`** (orchestrator applies `contract-change`), `openapi.json` + `frontend/src/api/schema.d.ts` (regenerated), `frontend/src/api/client.ts` + `frontend/mocks/` **only for the default-project aliases below**
- **Contract change:** yes — new routes, auth header, dependency
- **Benchmark delta expected:** none

## Goal
The API holds one project in a process global; a restart loses it, two replicas disagree, and there is
no user. Phase 3's gate is "two API replicas behind one URL, projects survive restart". This spec gives
the API a database, many projects, and a bearer token.

## Files
- Create `src/ngdesign/store/` — `models.py` (SQLModel tables: `ProjectRow(id, name, owner, body_json,
  created_at, updated_at, version)`, `ConversationRow(id, project_id, messages_json, updated_at)`,
  `SolveRow(id, project_id, project_hash, status, result_json, created_at)`), `db.py` (engine from
  `STOMATO_DATABASE_URL`, default `sqlite:///./stomato.db`; Postgres via `postgresql+psycopg://`;
  `init_db()`; sessions), `projects.py` (`DbProjectStore(ProjectStore)` bound to one project id;
  `list/create/get/update/delete`; optimistic `version` check on update → 409), `conversations.py`.
  No raw SQL; the pydantic `Project` is stored as JSON (`model_dump_json`) and validated on read.
- Edit `ngdesign.api`
  - `routes_projects.py`: `GET /api/projects`, `POST /api/projects` (body `Project` or `{name}` → the
    slice sample), `GET/PUT/DELETE /api/projects/{id}`, `POST /api/projects/{id}/reset`. Every existing
    project-scoped route gains a project-scoped twin under `/api/projects/{id}/...` (`solve`, `route`,
    `views/*`, `layout/*`, `export/*`, `agent`), implemented once: the handlers take the store from a
    FastAPI dependency `project_store(id)`.
  - The legacy unscoped routes (`/api/project`, `/api/solve`, …) stay as aliases bound to a project
    named `default` (created on first use) so the current frontend keeps working unchanged; `openapi.json`
    marks them `deprecated: true`.
  - Auth: `Authorization: Bearer <token>` required on every `/api/*` route except `/api/health` when
    `STOMATO_API_TOKENS` (comma-separated) is set; unset = open (local dev), logged once at startup. A
    token maps to an `owner` string (`token:owner` pairs); projects list only the owner's. 401/403 as
    usual.
  - CORS: `STOMATO_CORS_ORIGINS` (comma-separated), default `http://localhost:5173`; never `*`.
  - `routes_agent`: conversations persist in `ConversationRow`; the in-memory dict goes.
  - `app.py`: `init_db()` on startup; the process-global `_state` goes.
- CLI: `ngdesign serve` (uvicorn with the env above), `ngdesign db init|upgrade` (SQLModel
  `create_all`; a schema version table so a later Alembic migration can take over).
- Tests: `tests/store/` (CRUD, version conflict, JSON round-trip, Postgres via `STOMATO_TEST_DATABASE_URL`
  when set, SQLite otherwise), `tests/api/test_projects.py` (two projects isolated; restart = new app
  instance on the same SQLite file keeps the project; auth on/off; CORS header), existing `tests/api/`
  PASS unchanged through the aliases.

## Acceptance criteria
- [ ] Two `TestClient` app instances over one SQLite file see the same projects
- [ ] All tests above PASS; existing API tests unchanged; `openapi.json`/`schema.d.ts` regenerated; `check:api`, `typecheck`, frontend tests green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
User registration/password flows (static tokens only), per-project ACLs, the job queue (P3-02).
