# S-12: P&ID rule: isolation valve at every process nozzle

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `nozzle_isolation`

## Goal
Every line end that connects to an equipment nozzle gets a block valve adjacent to the nozzle.

## Files (create only these)
- `src/ngdesign/pid_rules/nozzle_isolation.py`
- `tests/pid_rules/test_nozzle_isolation.py`

## Method
For each PidLine end at equipment: walking the line's items from that end, an isolation VALVE
(type = the pipe class `default_isolation_valve` from `ngdesign.data.pipe_classes()`, same NPS as the
line, flange class of the pipe class) must appear before any item other than: check valves, DRAIN, VENT,
INSTRUMENT_TAP, reducers. (This lets the other rules insert those items without breaking this one.)
apply(): insert missing valves at the end of that allowed prefix; tag them `HV-<4-digit>` allocated above the max existing HV number
(start 1001). Must be idempotent and must not renumber existing valves.
check(): one RuleViolation per missing valve (rule="nozzle_isolation", target=line number).

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule (finds violations on bare sample, clean after apply, idempotent, composes with the other rules)
- [ ] Own tests: boundary ends get no valve; existing valve is not duplicated
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Valve sizing beyond line size; double block and bleed (not in v1).
