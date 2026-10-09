# B-04: API: P&ID SVG with placement

- **Depends on:** S-18, S-33, B-02
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
GET /api/views/pid.svg from builder + all rules (fixed point) with layout.pid overrides.

## Files
- `src/ngdesign/api/routes_pid.py`
- `tests/api/test_pid_view.py`

## Acceptance criteria
- [ ] Every tag/line number present; data-tag on equipment, valves, instruments, lines
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
