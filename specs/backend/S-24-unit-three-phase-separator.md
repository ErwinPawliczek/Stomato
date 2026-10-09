# S-24: Unit: three-phase separator

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `unit`, name `separator_3phase` (also register `scrubber` as a 2-phase variant)

## Goal
Split a feed into gas, hydrocarbon liquid and free water at inlet conditions.

## Files (create only these)
- `src/ngdesign/units/separator.py`
- `tests/units/test_separator.py`

## Method
Ports: inlet -> gas_out, hc_out, water_out (scrubber: inlet -> gas_out, liquid_out).
Optional param dP (Pa, default 0). Map phases by kind (vapor -> gas_out, hc_liquid -> hc_out,
aqueous -> water_out). PT flash at (T_in, P_in - dP); each outlet = that phase re-flashed at
the same T, P with its own composition and flow; an absent phase gives a zero-flow outlet whose composition
is the inlet composition (StreamState requires a valid composition). duty_W = sum(H_out*F) - H_in*F_in
(should be ~0 for dP = 0). example_case(): the slice inlet feed.

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for separator_3phase and scrubber
- [ ] Own tests: slice inlet gives non-zero gas, HC and water outlets; gas outlet is single-phase vapor
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Sizing (S-31).
