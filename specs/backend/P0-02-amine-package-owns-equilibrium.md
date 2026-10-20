# P0-02: Amine package owns its equilibrium code (break amine -> units)

- **Phase:** 0
- **Depends on:** none
- **Packages you may edit:** `ngdesign.amine`, `ngdesign.units` (only `mdea_equilibrium.py`, `mdea_absorber.py`, `mdea_regenerator.py`), `.importlinter` (delete lines only), `tests/units/`, `tests/amine/`
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
`ngdesign.amine.equilibrium` and `ngdesign.amine.enrtl` import from
`ngdesign.units.mdea_equilibrium` (a root finder `_brent_root` and Kent–Eisenberg pieces). The
chemistry/thermo of amine solutions belongs in `amine/` (it is a property model); unit operations
consume it. Reverse the dependency so `units -> amine`, never `amine -> units`.

## Files
- Create: `src/ngdesign/amine/roots.py` — `brent_root` (moved from `units/mdea_equilibrium.py`,
  made public, same algorithm, same tolerances).
- Create: `src/ngdesign/amine/kent_eisenberg.py` — every function/constant that
  `amine/equilibrium.py` currently imports from `units/mdea_equilibrium.py`, moved verbatim.
- Edit: `src/ngdesign/units/mdea_equilibrium.py` — becomes a thin unit-side adapter that imports
  from `ngdesign.amine.kent_eisenberg` / `ngdesign.amine.roots`. Keep every public name it
  exported so `mdea_absorber.py` / `mdea_regenerator.py` need no change (or update their imports
  if you prefer; either way no behaviour change).
- Edit: `src/ngdesign/amine/equilibrium.py`, `src/ngdesign/amine/enrtl.py` — import from the
  new amine modules. Fix the docstrings in `amine/__init__.py` and `enrtl.py` that describe the
  old direction.
- Edit: `.importlinter` — delete the two `P0-02` ignore lines.

## Method
Move, do not rewrite. Numerical results must be identical: the MDEA/MEA/DEA unit tests and
`tests/property/test_unit_balances.py` are the oracle. If a moved function had slice-specific
defaults, keep them exactly for now (P1 removes them).

## Acceptance criteria
- [ ] `grep -r "ngdesign.units" src/ngdesign/amine/` returns nothing
- [ ] The two P0-02 lines are gone from `.importlinter`; `uv run lint-imports` reports 0 broken
- [ ] All existing tests under `tests/units/` and `tests/amine/` (if present) PASS unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Changing the chemistry, promoting e-NRTL to a thermo plugin (Phase 1), touching `thermo/`.
