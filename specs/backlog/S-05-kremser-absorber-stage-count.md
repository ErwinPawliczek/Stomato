# S-05: Kremser absorber stage count

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `kremser`

## Goal
Implement the `kremser` correlation as a callable plugin. Golden cases already exist in `data/golden/kremser.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/kremser.py`
- `tests/sizing/test_kremser.py`

## Method
N = ln[((y_in - m*x_top)/(y_out - m*x_top))*(1 - 1/A) + 1/A] / ln(A); for |A - 1| < 1e-6 use the limit N = (y_in - y_out)/(y_out - m*x_top). Infeasible spec (y_out <= m*x_top) raises ValueError.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def kremser(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k kremser` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
