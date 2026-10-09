#!/usr/bin/env bash
# Start backend (:8000) and frontend (:5173) together. Ctrl-C stops both.
set -e
cd "$(dirname "$0")/.."
uv run uvicorn ngdesign.api.app:app --reload --port 8000 &
trap 'kill $!' EXIT
cd frontend && npm install --silent && npm run dev
