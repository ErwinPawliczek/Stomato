# U-H2: Refining reactors, R0 (lumped yield tables)

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01, U-F1 (`kinetics.yield_shift`, must be on main), U-H1's `slate.py` (or A-01
  directly)
- **Packages you may edit:**
  - `src/ngdesign/units/refining/reactors_*.py` (new modules only);
  - `data/unit_models/refining.yaml` (R0 levels of the five rows below only),
    `data/validation_units/refining/` (append your cases);
  - `tests/units/refining/`, generated `docs/units*`.
- **GitHub issue:** #214
- **Contract change:** no
- **Benchmark delta expected:** none

## Method
Every unit is a yield-table reactor at R0:
- `kinetics.yield_shift` with mass yields computed from a cited correlation of the unit's severity
  variable. The correlation is an equation with its constants (published numbers), never a digitised
  proprietary table.
- Rows use `balance: mass_elements`: mass on everything, and elements on the formula species. Pseudos
  are mass-only, as U-01 defines.
- Outlets at `T_out` and `P_out`. Heat of reaction: pseudo-components have no formation enthalpies, so
  R0 runs at the given outlet T and reports the duty on the package's enthalpy basis, flagged
  `heat_of_reaction_basis: "sensible-only (pseudo Hf unavailable)"` in info.
- Raise a GitHub issue proposing a pseudo-component Hf correlation as a thermo-layer contract change.
  Do not implement it.
- Hydrogen consumption comes from the correlation, with H2 as a real component on its own inlet port.

| id | severity variable and yield basis | candidate cited correlations |
|---|---|---|
| naphtha_ht | S and N removal to spec; H2 consumption from the S/N removed and olefin saturation; H2S and NH3 products (real components; S and N carried by declared feed `sulfur_wt`/`nitrogen_wt`) | Gary–Handwerk–Kaiser hydrotreating H2 consumption (scf/bbl per wt % S) |
| reformer_cat | C5+ yield vs research octane (severity) and feed N+2A | Gary–Handwerk–Kaiser reformer yield correlations (C5+ vol % vs RON) |
| fcc | product yields vs conversion (vol %) | Gary–Handwerk–Kaiser FCC yield correlations (gasoline, LCO, C3/C4, coke vs conversion) |
| hcu | product yields vs conversion and H2 consumption | Gary–Handwerk–Kaiser hydrocracker yield correlations |
| coker | coke, gas, naphtha and gasoil yields vs feed CCR (Conradson carbon) | Gary–Handwerk–Kaiser delayed-coker yield equations (coke wt % = 1.6·CCR, and so on) |

For each correlation:
- Type the equation and constants from the source and list each one in the PR body, with the edition and
  page.
- Where the open literature gives only a figure (no equation), the row stays planned. Record what was
  searched; do not digitise curves.

## V1
One worked example per unit from the same source (the book's example problems), within its rounding.

## Out of scope
R1 lumped kinetics (Smith reformer, Weekman FCC); heat balance with catalyst circulation; pseudo Hf.
