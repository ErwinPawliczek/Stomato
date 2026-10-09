# S-13: P&ID rule: check valve on pump and compressor discharge

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `discharge_check_valve`

## Goal
Prevent reverse flow: every line starting at a pump or compressor discharge nozzle has a check valve.

## Files (create only these)
- `src/ngdesign/pid_rules/discharge_check.py`
- `tests/pid_rules/test_discharge_check.py`

## Method
Equipment kinds `pump`, `compressor` (from PidEquipment.kind). The line whose start is that
equipment's discharge nozzle (nozzle.service == "discharge") must contain a CHECK valve
(check_dual_plate for NPS >= 3, check_swing otherwise) that comes before the first isolation
(non-check) valve when walking from the discharge end; insert it directly before that valve, or at the
start if there is none. Tags `CV-<4-digit>`. Idempotent.

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule
- [ ] Own tests: ordering relative to an existing block valve
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Pump minimum-flow line (not in v1).
