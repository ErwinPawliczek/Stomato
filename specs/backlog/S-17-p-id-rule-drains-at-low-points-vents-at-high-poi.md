# S-17: P&ID rule: drains at low points, vents at high points

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `pid_rule`, name `drains_vents`

## Goal
Every line connected to equipment gets a drain at its low end and a vent at its high end.

## Files (create only these)
- `src/ngdesign/pid_rules/drains_vents.py`
- `tests/pid_rules/test_drains_vents.py`

## Method
For lines with at least one equipment end: compare nozzle elevations (position_mm.z) of the two
ends (a boundary end counts as elevation 0). The line must contain a DRAIN item and a VENT item.
apply() inserts a missing DRAIN at the low end (index 0 if the start is lower, else appended) and a missing
VENT at the high end (equal elevations: drain at start, vent at end); check() only tests presence, so other
rules may insert items around them. Each item note = "3/4in DBB" for hydrocarbon fluid codes
(PG, PL, NG, FL) else "3/4in". Idempotent.

## Acceptance criteria
- [ ] `tests/property/test_pid_rules.py` PASSES for this rule
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Real 3D low/high point detection (piping layer does that later).
