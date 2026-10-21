# P3-03: Containers, compose for local, Helm chart, image build on tag

- **Phase:** 3
- **Depends on:** P3-01, P3-02
- **Packages you may edit:** `deploy/` (new), `Dockerfile` + `frontend/Dockerfile` (new), `.dockerignore`, `.github/workflows/release.yml` (new; orchestrator applies `contract-change`), `docs/deploy.md` (new), `README.md` (one section)
- **Contract change:** yes — `.github/` is locked
- **Benchmark delta expected:** none

## Goal
Phase 3's gate: two API replicas behind one URL, projects survive restart. Deployables per
docs/PLAN.md §2: `api`, `worker`, `web`, plus Postgres and Redis. (The deliverables service stays
in-process until it has a reason not to be; the chart leaves a disabled `deliverables` deployment.)

## Files
- `Dockerfile` (multi-stage: `uv` install → slim runtime; entrypoints `ngdesign serve` / `ngdesign
  worker`; non-root; healthcheck `/api/health`), `frontend/Dockerfile` (build → nginx serving `dist/`
  and proxying `/api` to the api service).
- `deploy/compose.yaml`: `api` (2 replicas behind the `web` nginx upstream), `worker`, `web`, `postgres`,
  `redis`; env from `deploy/.env.example`; `docker compose up` gives the whole app on `:8080`.
- `deploy/helm/stomato/`: `Chart.yaml`, `values.yaml` (image tags, replica counts, resources, tokens as
  a Secret, DATABASE_URL/REDIS_URL from Secrets, ingress host), templates for api Deployment+Service+HPA,
  worker Deployment, web Deployment+Service+Ingress, a Job for `ngdesign db init`, optional
  bundled Postgres/Redis (StatefulSets) toggled off when external URLs are given.
- `.github/workflows/release.yml`: on tag `v*`, build and push `ghcr.io/erwinpawliczek/stomato-api`,
  `-worker` (same image, different command), `-web`; `helm lint` + `helm template` on every PR
  touching `deploy/` (add that job to `ci.yml`).
- `docs/deploy.md`: compose quickstart, Helm install, env reference, how the gate was verified.
- Tests: `tests/deploy/test_compose.py` (`docker compose config` validates; skipped when docker is
  absent), `helm lint` in CI.

## Acceptance criteria
- [ ] `docker compose up` on a clean machine serves the app; killing one api replica keeps it working; `docker compose restart` keeps the projects
- [ ] `helm lint` and `helm template` clean; release workflow runs on a tag (dry-run verified with `act` or by the orchestrator)
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed paths changed
