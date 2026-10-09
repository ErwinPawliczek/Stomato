# B-02: API: /api/solve

- **Depends on:** S-01, S-24..S-30
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
Wire POST /api/solve: solve the current project with thermo `pr` + `sequential_modular`; cache by project hash.

## Files
- `src/ngdesign/api/routes_solve.py`
- `tests/api/test_solve.py`

## Acceptance criteria
- [ ] Returns SolvedFlowsheet for the slice; 501 if a unit kind is missing (message names it)
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
