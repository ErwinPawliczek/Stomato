# S-04: Counter-current LMTD

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `lmtd_counter`

## Goal
Implement the `lmtd_counter` correlation as a callable plugin. Golden cases already exist in `data/golden/lmtd_counter.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/lmtd.py`
- `tests/sizing/test_lmtd.py`

## Method
dT1 = Th_in - Tc_out, dT2 = Th_out - Tc_in, LMTD = (dT1 - dT2)/ln(dT1/dT2); if dT1 == dT2 (within 1e-9) return dT1. Temperature cross (dT <= 0) raises ValueError.

Also provide `ua_required(Q_W, lmtd_K, F=1.0) -> float` (Q = U*A*F*LMTD).

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def lmtd_counter(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k lmtd_counter` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
