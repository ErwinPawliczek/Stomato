# C-01: Chemistry engine (units of measure, cited database, reaction and phase depth)

- **Phase:** 5 (docs/PLAN.md: Breadth), plus the Phase 1 "unit-of-measure layer" still marked ❌ in §7
- **Depends on:** U-R (reaction contract), T-01 (thermo catalogue)
- **Packages you may edit:** `ngdesign.uom` (new), `ngdesign.chem` (new), `ngdesign.data.chemdb` (new module), `ngdesign.cli` (one hook), `ngdesign.units._physics.kinetics` (`heat_of_reaction` root fix, exact at 298.15 K), `scripts/chemdb/`, `data/chemdb/`, `.importlinter` (two new layers), `tests/uom/`, `tests/chem/`, `tests/data/test_chemdb.py`, `docs/chem-engine.md`
- **Contract change:** no
- **Benchmark delta expected:** none; no flowsheet path changes
- **GitHub issue:** none (requested directly by the maintainer)

## Goal
Turn the gas-processing engine's chemistry into a general one: any of ~18k cited species,
units checked at every edge, and exact stoichiometry, reaction thermochemistry, multiphase
equilibrium, stiff kinetics and phase behaviour, all reusing the existing contracts and
thermo packages.

## Files
- Create: `src/ngdesign/uom/{dimension,units,quantity,sets}.py`,
  `src/ngdesign/chem/{formula,stoichiometry,thermochem,equilibrium,kinetics,phase,cli}.py`,
  `src/ngdesign/data/chemdb.py`, `scripts/chemdb/{fetch,parse_nist,build}.py`, `data/chemdb/*`
- Edit: `src/ngdesign/cli.py` (register `chem`), `.importlinter` (`chem` above `units`, `uom` below `data`)

## Method
Equations and sources are in each module docstring; `docs/chem-engine.md` is the overview.
Data rules: a database row is a number a named source states, converted to SI. Nothing is
estimated. All sources are kept and one is selected by grade; disagreements go to `AUDIT.txt`.

## Acceptance criteria
- [ ] `ngdesign.uom`: exact definitions (NIST SP 811), offset scales, gauge pressure, standard gas volumes, basis changes behind explicit `mw=`/`rho=`, dimension refusals: `tests/uom/`
- [ ] `data/chemdb`: every row cites a known source; one selected per (species, property); CAS check digits valid; critical points match CoolProp: `tests/data/test_chemdb.py`
- [ ] Balancing exact over the rationals, including redox and charge: `tests/chem/test_stoichiometry.py`
- [ ] Reaction thermochemistry reproduces JANAF log Kf and measured heats of combustion: `tests/chem/test_thermochem.py`
- [ ] Multiphase Gibbs solver satisfies every independent reaction, and agrees with `units._physics.gibbs` on potentials it shares: `tests/chem/test_equilibrium.py`
- [ ] Kinetics match closed forms, and an independent integrator on Robertson: `tests/chem/test_kinetics.py`
- [ ] Saturation matches CoolProp; azeotrope and envelope run through registered packages: `tests/chem/test_phase.py`
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] No flowsheet result changes: `tests/e2e/test_slice.py` and the bench goldens untouched

## Out of scope
Migrating `units._physics.gibbs` and `data.formation` onto this layer, flowsheet units over
the new solver, HTTP routes (they change `openapi.json` and need a paired frontend PR).
