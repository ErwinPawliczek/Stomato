# S-14: P&ID rule: PSV on every pressure vessel

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `vessel_psv`

## Goal
Every pressure vessel has a relief valve set at its design pressure, discharging to the flare header.

## Files (create only these)
- `src/ngdesign/pid_rules/vessel_psv.py`
- `tests/pid_rules/test_vessel_psv.py`

## Method
Pressure vessels: PidEquipment.kind in {separator_3phase, scrubber, teg_contactor,
amine_contactor, flash_drum, reflux_drum, ko_drum}. The vessel's nozzle with service "psv" gets a
Valve(type=PSV, tag PSV-<4-digit>, set_pressure_Pa = design_pressure_Pa, nps = nozzle nps) and a new PidLine
from that nozzle to boundary "FLARE" with fluid code "FL", pipe class of the vessel inlet line, number
`<nps>"-FL-<seq>-<class>` (sequence above max existing). If the vessel has no "psv" nozzle, check() reports it
and apply() leaves it (nozzles are owned by sizers).

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule
- [ ] Own tests: set pressure equals design pressure; line number format valid
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Relief load calculation and PSV sizing (S-34).
