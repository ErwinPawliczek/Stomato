# S-28: Units: JT valve, mixer, splitter

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `unit`, names `jt_valve`, `mixer`, `splitter`

## Goal
Basic topology and isenthalpic expansion units.

## Files (create only these)
- `src/ngdesign/units/jt_valve.py`
- `src/ngdesign/units/mixer.py`
- `src/ngdesign/units/splitter.py`
- `tests/units/test_basic_units.py`

## Method
jt_valve: inlet -> outlet, param P_out; outlet = flash_ph(z, P_out, h_in); info dT_K.
mixer: inlet_1..inlet_N (class attribute inlet_ports = ("inlet_1","inlet_2","inlet_3"); unused ports may be
zero-flow) -> outlet at min inlet P, enthalpy-weighted flash_ph.
splitter: inlet -> outlet_1, outlet_2; param fractions [f1, f2] summing to 1; same T, P, composition.

## Acceptance criteria
- [ ] `tests/property/test_unit_balances.py` PASSES for all three
- [ ] Own test: JT of the slice gas from 7 MPa to 3 MPa cools it (dT < 0)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Valve Cv (S-10).
