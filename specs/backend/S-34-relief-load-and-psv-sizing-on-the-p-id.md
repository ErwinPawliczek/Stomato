# S-34: Relief load and PSV sizing on the P&ID

- **Wave:** 2
- **Depends on:** S-09, S-14, S-33
- **Plugin:** kind `pid_rule`, name `psv_sizing` (runs after vessel_psv)

## Goal
Size every PSV for blocked outlet and fire case and record the API 526 orifice.

## Files (create only these)
- `src/ngdesign/pid_rules/psv_sizing.py`
- `tests/pid_rules/test_psv_sizing.py`

## Method
Blocked outlet load = max inlet flow; fire case Q = 21000*F*A_wet^0.82 (API 521, USC, F = 1)
with wetted area from the vessel datasheet. Relieving pressure = 1.1 x set (1.21 x for fire). Area via S-09,
orifice letter via api526_orifice. Store orifice in the Valve note field; check() flags PSVs without sizing.

## Acceptance criteria
- [ ] Own tests on a sized slice V-101; test_pid_rules invariants pass
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Liquid relief, two-phase relief.
