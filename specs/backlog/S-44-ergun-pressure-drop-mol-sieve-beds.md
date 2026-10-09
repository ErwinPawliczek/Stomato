# S-44: Ergun pressure drop (mol sieve beds)

- **Wave:** stretch
- **Depends on:** none
- **Plugin:** kind `correlation`, name `ergun`

## Goal
Packed-bed pressure drop.

## Files (create only these)
- `src/ngdesign/sizing/ergun.py`
- `tests/sizing/test_ergun.py`

## Method
dP/L = 150 mu v (1-e)^2/(e^3 d^2) + 1.75 rho v^2 (1-e)/(e^3 d); cross-check with fluids.packed_bed.

## Acceptance criteria
- [ ] Agrees with fluids.packed_bed.Ergun within 1e-9
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Bed sizing.
