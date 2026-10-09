# B-05: API: plot plan + routing

- **Depends on:** S-21, B-04
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
GET /api/views/plot.svg (top view) and POST /api/route using layout.plot.

## Files
- `src/ngdesign/api/routes_plot.py`
- `tests/api/test_plot.py`

## Acceptance criteria
- [ ] Moving equipment in layout.plot changes routed lengths
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
