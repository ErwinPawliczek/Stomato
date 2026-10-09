# S-10: Control valve Cv (liquid, non-choked)

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `cv_liquid`

## Goal
Implement the `cv_liquid` correlation as a callable plugin. Golden cases already exist in `data/golden/cv_liquid.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/control_valve.py`
- `tests/sizing/test_control_valve.py`

## Method
Cv = Q[gpm]*sqrt(SG/dP[psi]).

Also provide an SI wrapper using `fluids.control_valve.size_control_valve_l` for full ISA/IEC 60534 sizing, with a test that it agrees with the simple formula within 5% for a non-choked turbulent case.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def cv_liquid(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k cv_liquid` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
