# Deploying Stomato (spec P3-03)

Three deployables per `docs/PLAN.md` §2 — `api` (the FastAPI server), `worker`
(the solve-job worker; same image, different command), `web` (nginx serving the
built React app and proxying `/api` to the api service) — plus Postgres
(projects, conversations, solve results) and Redis (job queue).

Two ways to run it:

| | docker compose | Helm |
|---|---|---|
| Purpose | local development / single-box demo | cluster deployment |
| Postgres/Redis | bundled services in the compose file | bundled StatefulSets, skipped when external URLs are set |
| Entry | `docker compose up` → http://localhost:8080 | `helm install` (Ingress or port-forward) |
| Images | built from source on `up` | GHCR images, built by tagging `v*` |

## Compose quickstart

```sh
docker compose -f deploy/compose.yaml up --build
# open http://localhost:8080
```

That brings up `postgres`, `redis`, a one-shot `db-init` (runs
`ngdesign db-init`; the api replicas start only after it succeeds),
2 × `api` behind the `web` nginx upstream, one `worker`, and `web`.

Configuration: copy `deploy/.env.example` to `deploy/.env` and edit — the
compose file substitutes `${VAR:-default}` from it. Defaults give an open
(token-less) local install.

```sh
docker compose -f deploy/compose.yaml down          # stop (keeps pgdata)
docker compose -f deploy/compose.yaml restart       # projects survive (they live in Postgres)
```

## Helm install

```sh
helm install stomato deploy/helm/stomato -f deploy/helm/stomato/values-local.yaml
kubectl -n default port-forward svc/stomato-stomato-web 8080:80
```

`values-local.yaml` is the worked local example (bundled Postgres/Redis, open
auth). Production shape:

```sh
helm install stomato deploy/helm/stomato \
  --set ingress.host=stomato.example.com \
  --set cors.origins=https://stomato.example.com \
  --set auth.tokens="$STOMATO_API_TOKENS" \
  --set postgres.url=postgresql+psycopg://stomato:$PW@db.internal:5432/stomato \
  --set redis.url=redis://cache.internal:6379/0
```

What the chart deploys: an api Deployment + Service + optional HPA
(`api.autoscaling.enabled`, off by default), a worker Deployment, a web
Deployment + Service + Ingress, a pre-install/upgrade Job that runs
`ngdesign db-init`, and Postgres/Redis StatefulSets (+ headless Services)
that disappear the moment `postgres.url` / `redis.url` is set. One config
Secret carries `STOMATO_API_TOKENS`, `STOMATO_CORS_ORIGINS`,
`STOMATO_DATABASE_URL`, `STOMATO_REDIS_URL` and (when bundled) a generated
Postgres password; every workload reads it via `envFrom`.

## Images

On a `v*` tag, `.github/workflows/release.yml` builds and pushes to GHCR:

- `ghcr.io/erwinpawliczek/stomato-api:<ver>` — backend (`ngdesign serve`)
- `ghcr.io/erwinpawliczek/stomato-worker:<ver>` — same image, worker tag
- `ghcr.io/erwinpawliczek/stomato-web:<ver>` — nginx + built `dist/`

All are non-root; the backend image has a Docker `HEALTHCHECK` on
`/api/health` (disabled for the worker container in compose — the worker
serves no HTTP; Kubernetes ignores Docker HEALTHCHECKs, the chart probes the
api Deployment directly). Base images are pinned by tag:
`python:3.12.8-slim-bookworm`, `ghcr.io/astral-sh/uv:0.5.22`,
`node:22.13.0-alpine`, `nginx:1.27.3-alpine`, `postgres:17.2-alpine`,
`redis:7.4.2-alpine`.

## Environment reference

| Variable | Set by | Meaning |
|---|---|---|
| `STOMATO_DATABASE_URL` | chart Secret / compose `.env` | SQLAlchemy URL; `postgresql+psycopg://…` in any deployment, `sqlite:///./stomato.db` for bare local dev |
| `STOMATO_REDIS_URL` | chart Secret / compose `.env` | Redis URL for the solve-job queue |
| `STOMATO_API_TOKENS` | chart Secret / compose `.env` | comma-separated `token:owner` bearer tokens; unset = open local mode |
| `STOMATO_CORS_ORIGINS` | chart Secret / compose `.env` | comma-separated allowed browser origins; `*` is rejected |
| `POSTGRES_PASSWORD` | compose `.env` | password of the bundled compose Postgres |

## How the Phase 3 gate was verified

Gate: *two API replicas behind one URL, projects survive restart, a 10-minute
solve shows progress.*

- **Two replicas behind one URL:** `deploy/compose.yaml` runs
  `api` ×2 behind the `web` nginx upstream on :8080;
  `tests/deploy/test_compose.py` asserts the shape via
  `docker compose config`, and the chart's api Deployment defaults to
  `replicas: 2`.
- **Projects survive restart:** state lives in Postgres (P3-01 store) and the
  queue in Redis (P3-02), both with persistent volumes in compose; `restart`
  and container replacement do not touch project data.
- **Progress on long solves:** P3-02's SSE endpoint (`GET /jobs/{id}`) is
  reached through `web`'s nginx proxy, configured with
  `proxy_buffering off` and a 3600 s read timeout.
- **What was actually executed for this spec:** `helm lint` (clean),
  `helm template` (clean, incl. HPA-on and external-Postgres/Redis
  permutations), and `docker compose -f deploy/compose.yaml config`
  (valid) with docker compose v2.32.4 and helm v3.16.4 locally. No
  `docker compose up` was run here — the sandbox has no Docker daemon; the
  live kill-a-replica/restart check runs wherever Docker is available, or is
  verified by the orchestrator. CI runs the compose config validation and
  the Helm lint/template job on every deployables change.
