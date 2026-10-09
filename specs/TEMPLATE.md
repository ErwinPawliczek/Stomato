# S-XX: <title>

- **Wave:** 0 (start immediately) | 1 (after deps merge) | 2 | stretch
- **Depends on:** S-YY, ... (merged to main) or none
- **Plugin:** kind `<kind>`, name `<name>`

## Goal
One or two sentences: what this adds and why.

## Files (create only these)
- `src/ngdesign/<layer>/<module>.py`
- `tests/<layer>/test_<module>.py`

## Method
Equations / rules with sources. Units. Edge cases.

## Acceptance criteria
- [ ] Oracle test(s) `<path::name>` PASS (not skipped)
- [ ] Own tests cover: <cases>
- [ ] ruff, mypy, full `pytest -rs` green
- [ ] No locked file touched

## Out of scope
What not to do.
