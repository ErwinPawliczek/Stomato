# S-03: Souders-Brown gas capacity

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `souders_brown`

## Goal
Implement the `souders_brown` correlation as a callable plugin. Golden cases already exist in `data/golden/souders_brown.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/souders_brown.py`
- `tests/sizing/test_souders_brown.py`

## Method
`v_max = K*sqrt((rhoL - rhoG)/rhoG)`; minimum vertical vessel diameter `D = sqrt(4*Q/(pi*v_max))`.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def souders_brown(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k souders_brown` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
