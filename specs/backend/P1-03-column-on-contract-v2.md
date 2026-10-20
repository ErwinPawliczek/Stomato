# P1-03: Column consumes contract v2; split the god-file

- **Phase:** 1
- **Depends on:** P1-01, P0-06
- **Packages you may edit:** `ngdesign.units` (`column.py` → `column/` package), `tests/units/`, `bench/baseline.json` (update with `--update`, state the delta in the PR), `scripts/bench_baseline.py` + `tests/bench/` **only to make `CountingThermo` count the v2 methods** (see Method)
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

## What P1-01 actually landed (read before starting)
- `contracts/thermo.py`: `PhaseProps`, `SaturationPoint`, `PropertyDerivatives`, `SaturationError`.
  `Phase` carries `enthalpy`, `entropy`, `cp`, `ln_phi`; `Phase` and `StreamState` are **frozen**
  (the package caches and shares them — never mutate, use `model_copy(update=...)`).
- `thermo/cubic.py` `ThermoSurfaceMixin` implements the surface for every package; `flash_pt` and
  `phase_props` are LRU-cached per package instance (key: composition 1e-10, T 1e-6, P 1e-3).
  `k_values`, `bubble_point`, `dew_point`, `flash_tvf/pvf` are **not** cached and each costs one or
  more PT flashes internally (`bubble_point` ≈ 10–40). `derivatives` is one single-phase build.
- Saturation is a bracketed secant on the PT flash's vapour fraction (`thermo/_state.py`); the
  bracket comes from Wilson bounds. Supercritical feeds raise `SaturationError` — the column must
  catch it where it seeds temperatures and fall back to the Clausius–Clapeyron estimate.

## Method
**Counting.** `CountingThermo` (P0-06) counts only `flash_pt/ph/ps`; `k_values` and
`bubble_point` call the flash *inside* the package, below the proxy, so a column that simply
switches to `thermo.k_values` would show zero flashes without doing less work. Extend
`CountingThermo` to count every protocol method separately (`k_values`, `bubble_point`,
`dew_point`, `flash_tvf`, `flash_pvf`, `phase_props`, `derivatives`, `pure_psat`) and define the
benchmark's `flashes` as `flash_pt + flash_ph + flash_ps + k_values + bubble_point + dew_point +
flash_tvf + flash_pvf` (flash-equivalent calls; `phase_props` / `derivatives` / `pure_psat` are
reported in a separate `props` counter and are not budgeted). Existing baseline numbers are
unchanged by this definition because no existing case calls the v2 methods. The −85 % gate and
`test_flash_budget.py` apply to the flash-equivalent count. Prefer `k_values` over your own PT
flash only where the column needs K alone; where it needs K **and** phase enthalpies at the same
state, one `flash_pt` (cached) plus reading `Phase.enthalpy` / `.cp` / `.ln_phi` is cheaper than
`k_values` + two `phase_props`.

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
