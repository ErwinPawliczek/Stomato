# S-16: P&ID rule: pump instrumentation

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `pump_instruments`

## Goal
Every pump has pressure indicators on suction and discharge.

## Files (create only these)
- `src/ngdesign/pid_rules/pump_instruments.py`
- `tests/pid_rules/test_pump_instruments.py`

## Method
For each PidEquipment with kind "pump": a PI instrument connected to the suction line and one
to the discharge line (connected_to = line number), plus an INSTRUMENT_TAP inline item referencing each PI
tag on those lines. Same loop allocation scheme as S-15 (scan existing instruments for max loop).

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Minimum-flow recirculation.
