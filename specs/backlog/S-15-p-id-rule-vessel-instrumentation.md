# S-15: P&ID rule: vessel instrumentation

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `vessel_instruments`

## Goal
Every separator has level transmitter, gauge, high-high and low-low switches; every pressure vessel has a pressure transmitter.

## Files (create only these)
- `src/ngdesign/pid_rules/vessel_instruments.py`
- `tests/pid_rules/test_vessel_instruments.py`

## Method
Separators (kind contains "separator", "scrubber", "drum"): LT, LG, LSHH, LSLL; three-phase
separators get these per liquid (HC and interface: add LIT for interface). All pressure vessels: PT.
Tags ISA S5.1: `<FUNC>-<loop>` with one loop number per measured variable per vessel, loops allocated
sequentially from 1001 above the max existing loop. connected_to = vessel tag.

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule
- [ ] Own tests: tags match INSTR_TAG_RE; loop numbers unique per variable
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Control loops to valves (not in v1).
