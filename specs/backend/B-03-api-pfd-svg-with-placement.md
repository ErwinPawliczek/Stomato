# B-03: API: PFD SVG with placement

- **Depends on:** S-22, B-02
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
GET /api/views/pfd.svg renders the PFD using layout.pfd overrides; every unit/stream group carries data-tag.

## Files
- `src/ngdesign/api/routes_views.py`
- `tests/api/test_views.py`

## Acceptance criteria
- [ ] Placed tag renders at the stored position; unplaced tags auto-layout
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
