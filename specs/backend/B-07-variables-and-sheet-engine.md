# B-07: Variables + sheet engine

- **Depends on:** B-02
- **Note:** new routes change openapi.json, so this PR needs the `contract-change` label and a human merge.
  Register routes with `app.include_router(...)` in a single line added to `api/app.py`.

## Goal
Address every quantity (S-003.T, K-101.power, V-101.diameter); safe formula evaluator (ast, arithmetic + min/max/abs/sqrt only); POST /api/sheet/eval; POST /api/case-study (sweep one param, collect outputs).

## Files
- `src/ngdesign/variables.py`
- `src/ngdesign/api/routes_sheet.py`
- `tests/test_variables.py`

## Acceptance criteria
- [ ] Unknown address -> per-cell error, never 500
- [ ] Formulas cannot execute arbitrary code (test with __import__)
- [ ] Case study of K-101.P_out gives monotonic power
- [ ] ruff, mypy, pytest green; openapi.json regenerated (label contract-change, human merges)
