# S-31: Sizer: separators and vessels

- **Wave:** 2
- **Depends on:** S-03, S-30
- **Plugin:** kind `sizer`, names for unit kinds `separator_3phase`, `scrubber`, `teg_contactor`

## Goal
Size vessels and produce datasheets with nozzle tables.

## Files (create only these)
- `src/ngdesign/sizing/vessels.py`
- `tests/sizing/test_vessels.py`

## Method
Horizontal 3-phase separator: gas capacity by Souders-Brown (K = 0.12 m/s horizontal,
VERIFY), liquid volume from retention times (HC 3 min, water 5 min, VERIFY), L/D from 3 to 5,
diameter rounded up to 0.15 m. Vertical scrubber / contactor: Souders-Brown diameter (contactor K from
param, default 0.06 m/s for packing, VERIFY). Design pressure = max(operating P * 1.1, operating P + 170 kPa);
design T = operating T + 25 K. Nozzles: one per sim port (service = port name) sized with line_size (S-20) if
merged else velocity 10 m/s gas / 1 m/s liquid, plus psv, drain, vent, level and pressure taps; positions on
the shell (document the convention). Flange class = min_flange_class (S-11) if merged else 300.

## Acceptance criteria
- [ ] Own tests: slice V-101 diameter between 1.0 and 3.0 m, L/D in [3, 5]; every sim port has a nozzle; a psv nozzle always exists
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Internals.
