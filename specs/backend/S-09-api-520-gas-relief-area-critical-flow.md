# S-09: API 520 gas relief area (critical flow)

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `psv_api520_gas`

## Goal
Implement the `psv_api520_gas` correlation as a callable plugin. Golden cases already exist in `data/golden/psv_api520_gas.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/psv_gas.py`
- `tests/sizing/test_psv_gas.py`

## Method
USC units per golden file: C = 520*sqrt(k*(2/(k+1))^((k+1)/(k-1))); A[in2] = W/(C*Kd*P1*Kb*Kc)*sqrt(T*Z/M).

Also provide `api526_orifice(area_in2) -> str` returning the smallest standard API 526 letter orifice (D..T) whose area >= required; take the area table from fluids (`fluids.safety_valve.API526_letters`/`API526_A`) rather than typing it.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def psv_api520_gas(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k psv_api520_gas` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
