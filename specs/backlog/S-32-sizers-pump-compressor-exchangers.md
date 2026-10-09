# S-32: Sizers: pump, compressor, exchangers

- **Wave:** 2
- **Depends on:** S-04, S-08, S-30
- **Plugin:** kind `sizer`, names for `pump`, `compressor`, `air_cooler`, `shell_tube`

## Goal
Datasheets with nozzle tables for rotating and heat-transfer equipment.

## Files (create only these)
- `src/ngdesign/sizing/machines.py`
- `tests/sizing/test_machines.py`

## Method
Pump: rated flow 1.1x, head, NPSHa (S-08), motor kW rounded up to standard size list.
Compressor: power, discharge T, stages if ratio per stage > 3.5. Exchangers: area from UA with U defaults
(gas cooling 300 W/m2K, liquid 600, VERIFY) and LMTD (S-04) with utility air 35 C in, 15 K rise.
Nozzle sets: suction/discharge for machines, in/out for exchangers (plus vent/drain).

## Acceptance criteria
- [ ] Own tests: one case per kind with hand-checked numbers; nozzles cover every sim port
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Vendor selection.
