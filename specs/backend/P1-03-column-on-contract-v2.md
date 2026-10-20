# P1-03: Column consumes contract v2; split the god-file

- **Phase:** 1
- **Depends on:** P1-01, P0-06
- **Packages you may edit:** `ngdesign.units` (`column.py` → `column/` package), `tests/units/`, `bench/baseline.json` (update with `--update`, state the delta in the PR)
- **Contract change:** no
- **Benchmark delta expected:** column case: flashes −85 % or better; slice/recycle: none

## Goal
`units/column.py` (2265 lines) is a god-file holding parsing, a thermo adapter (`_ThermoBox`),
two solvers (inside-out, Naphtali–Sandholm), linear algebra (Thomas, Gauss) and the spec
layer. `_ThermoBox` rebuilds K-values, phase enthalpies and bubble temperatures from PT flashes
(2–10 flashes per stage per sweep, exact-float memo that rarely hits). With contract v2 those
are single calls. Target: same converged answers, ≤ 15 % of today's flash count.

## Files
- Create package `src/ngdesign/units/column/` with:
  - `__init__.py` — re-exports `Column` (the registered unit), `ColumnSpecError`,
    `ColumnConvergenceError` so every existing import path keeps working. (Registry discovery
    walks packages; confirm `registry.available("unit")` still lists `column`.)
  - `spec.py` — params parsing, pressure profile, feeds/draws/specs (moved).
  - `thermo_adapter.py` — the `_ThermoBox` replacement, now thin: `k_values` → `thermo.k_values`
    (fallback `k_estimate` only when `None`), `phase_enthalpy` → `thermo.phase_props(...).enthalpy`
    and `.cp` (no straddling flashes), `bubble_temperature` → `thermo.bubble_point(z, P=P).T`,
    `pure_psat` → `thermo.pure_psat`. Keep the Clausius–Clapeyron estimate as the documented
    fallback only.
  - `inside_out.py`, `naphtali_sandholm.py`, `linalg.py`, `specs.py` (spec secant / Broyden
    loop) — moved, not rewritten.
- Delete: `src/ngdesign/units/column.py`.
- Tests: all of `tests/units/test_column*.py` must pass **unchanged** except import paths if the
  test imports private names (`_ThermoBox`); update those imports only.
- Add `tests/units/column/test_flash_budget.py`: solve the column `example_case()` through the
  P0-06 `CountingThermo` proxy and assert flashes ≤ 0.15 × the pre-change number recorded in
  `bench/baseline.json` (read the number from the baseline, do not hard-code).

## Method
Behaviour: converged stage profiles for every existing column test within the tests' existing
tolerances; no tolerance changes. If a test only passes because of the old approximate
enthalpy model, that is a finding — report it in the PR with both numbers, do not loosen.

## Acceptance criteria
- [ ] `units/column.py` gone; `units/column/` package with the modules above; no file > 600 lines
- [ ] All existing column tests PASS; `tests/property/test_unit_balances.py` PASS
- [ ] `test_flash_budget.py` PASS; `bench/baseline.json` updated with the new column numbers and the PR states old → new flashes and wall time
- [ ] `tests/e2e/test_slice.py` byte-identical (slice has no column; confirms no collateral)
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Reactive/3-phase stages, pumparounds, side strippers (Phase 5), amine packages (P1-04).
