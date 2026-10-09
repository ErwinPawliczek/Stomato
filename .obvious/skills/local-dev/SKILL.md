---
name: local-dev
description: Install, run and verify ngdesign locally (backend + frontend). Use before any code change.
---
Backend (repo root):  uv sync --all-groups
  verify: uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -rs
  API:    uv run uvicorn ngdesign.api.app:app --port 8000
  after changing API routes: uv run python scripts/export_openapi.py
Frontend (frontend/): npm ci
  verify: npm run check:api && npm run typecheck && npm run lint && npm test && npm run build
  run against mocks: VITE_MOCK=1 npm run dev
