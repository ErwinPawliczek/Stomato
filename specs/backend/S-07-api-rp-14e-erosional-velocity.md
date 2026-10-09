# S-07: API RP 14E erosional velocity

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `erosional_api14e`

## Goal
Implement the `erosional_api14e` correlation as a callable plugin. Golden cases already exist in `data/golden/erosional_api14e.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/erosional.py`
- `tests/sizing/test_erosional.py`

## Method
v_e[ft/s] = C/sqrt(rho_m[lb/ft3]); inputs and outputs in SI (convert with 1 kg/m3 = 0.0624279606 lb/ft3, 1 ft = 0.3048 m).

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def erosional_api14e(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k erosional_api14e` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
