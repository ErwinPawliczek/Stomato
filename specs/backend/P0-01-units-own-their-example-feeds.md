# P0-01: Units own their example feeds (break units -> flowsheets)

- **Phase:** 0
- **Depends on:** none
- **Packages you may edit:** `ngdesign.units`, `ngdesign.flowsheets`, `.importlinter` (delete lines only), `tests/units/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** see task

## Goal
Six unit modules import constants from `ngdesign.flowsheets.slice` (`INLET_COMPOSITION`,
`MMSCFD_TO_MOL_S`, and whatever else each imports) only to build `example_case()`. That makes the
unit-operation layer depend on a sample flowsheet, which is upside-down: flowsheets are built
*from* units. Move the shared example basis into the units package and make the slice import it.

## Files
- Create: `src/ngdesign/units/_examples.py` — the example basis (composition, conversion
  constants, any helper the six modules currently pull from `flowsheets.slice`). Pure data +
  pure functions. Docstring states these are *example* values for `example_case()` and tests,
  not engineering defaults.
- Edit: `src/ngdesign/units/{separator,jt_valve,expander,heat_exchange,compression_train,compressor}.py`
  — import from `ngdesign.units._examples` instead of `ngdesign.flowsheets.slice`.
- Edit: `src/ngdesign/flowsheets/slice.py` — import the same names from `ngdesign.units._examples`
  so there is one definition. Values must not change.
- Edit: `.importlinter` — delete the six `P0-01` ignore lines.

## Method
Mechanical move. `grep -n "flowsheets.slice" src/ngdesign/units/*.py` lists every import; every
symbol in those imports is defined once in `_examples.py`. Run `uv run lint-imports` to confirm
`ngdesign.units -> ngdesign.flowsheets` no longer appears.

## Acceptance criteria
- [ ] `grep -r "flowsheets" src/ngdesign/units/` returns nothing
- [ ] The six P0-01 lines are gone from `.importlinter`; `uv run lint-imports` reports 0 broken
- [ ] `tests/property/test_unit_balances.py` and `tests/e2e/test_slice.py` PASS unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Changing any example value, any unit physics, or `flowsheets/samples.py`.
