# B-06: API: isometrics

- **Depends on:** S-19, B-05
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
GET /api/lines, GET /api/iso/{line_number} -> IsoSheet.

## Files
- `src/ngdesign/api/routes_iso.py`
- `tests/api/test_iso.py`

## Acceptance criteria
- [ ] Lengths/BOM invariants hold for every line of the slice
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
