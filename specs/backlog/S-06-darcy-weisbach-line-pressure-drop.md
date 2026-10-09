# S-06: Darcy-Weisbach line pressure drop

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `darcy_colebrook`

## Goal
Implement the `darcy_colebrook` correlation as a callable plugin. Golden cases already exist in `data/golden/darcy_colebrook.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/line_friction.py`
- `tests/sizing/test_line_friction.py`

## Method
v = Q/A, Re = rho*v*D/mu, Darcy f from Colebrook (use `fluids.friction.Colebrook`; laminar Re < 2300 -> 64/Re), dP = f*(L/D)*rho*v^2/2.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def darcy_colebrook(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k darcy_colebrook` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
