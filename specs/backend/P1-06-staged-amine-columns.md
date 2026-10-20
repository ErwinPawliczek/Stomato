# P1-06: Staged amine absorber and regenerator on the rigorous column

- **Phase:** 1
- **Depends on:** P1-03 (column on contract v2, `units/column/` package), P1-04 (`amine_ke` / `amine_enrtl` thermo packages)
- **Packages you may edit:** `ngdesign.units` (new `units/amine_column.py`; `mdea_absorber.py` / `mdea_regenerator.py` only to add the `mode="staged"` dispatch), `ngdesign.flowsheets` (new sample only), `tests/units/`, `tests/e2e/` (new file only), `bench/baseline.json` (add the new case with `--update`; existing cases unchanged), `scripts/bench_baseline.py` (only to register the new case)
- **Contract change:** no
- **Benchmark delta expected:** existing cases none; one new case `amine_staged` (state its numbers in the PR)

## Goal
The amine units are single-equilibrium-stage shortcuts: the absorber removes acid gas to a spec and
checks feasibility against Kent–Eisenberg bounds; the regenerator inverts the same equilibrium at the
reboiler temperature. Neither has stages, so stage count, lean-amine temperature bulge, rich-loading
profile and reboiler duty vs stripping steam cannot be designed. With P1-03 (a stage-by-stage column
that only talks to the `Thermo` protocol) and P1-04 (amine chemistry *is* a `Thermo` package), a
staged amine column is a column solve with the amine package — no new numerics. This spec wires that
up and proves it against the shortcut units.

## Files
- Create: `src/ngdesign/units/amine_column.py`
  - `@register("unit", "amine_absorber")` — ports `gas_in`, `lean_amine_in` → `gas_out`,
    `rich_amine_out`. Params: `n_stages` (default 20), `P` or `pressure_profile` (default: gas
    inlet P, no drop), `murphree_efficiency` (default 1.0, applied per stage to the vapour
    composition, Murphree 1925; document), `thermo` override name (default: the flowsheet's thermo,
    which must be an amine package — raise a typed `AmineColumnSpecError` naming the registered
    amine packages when it is a plain cubic).
    Implementation: build the P1-03 column with `condenser="none"`, `reboiler="none"`, gas fed to
    stage N, lean amine to stage 1, no specs (a feed-determined absorber has zero tears), and run
    it with the amine package. Map stage-1 vapour → `gas_out`, stage-N liquid → `rich_amine_out`.
    Report in `info`: per-stage T profile (`stage_T_K: list`), rich loading `rich_co2_loading`,
    `rich_h2s_loading`, `lean_co2_loading`, outlet `outlet_co2_molpct`, `outlet_h2s_ppmv`,
    `heat_of_absorption_W` (from the package, P1-04), `temperature_bulge_K` (max stage T − lean
    inlet T) and `n_stages`.
  - `@register("unit", "amine_regenerator")` — ports `rich_amine_in` → `lean_amine_out`,
    `acid_gas_out`. Params: `n_stages` (default 20), `regenerator_P` (default 1.9 bara, same as
    the shortcut), `condenser` (`"partial"` default, reflux returns water; or `"none"`),
    `reboiler="kettle"`, specs: exactly one of `reboiler_duty_W`, `lean_co2_loading` (default:
    the shortcut's `DEFAULT_LEAN_CO2_LOADING`), or `steam_ratio_kg_per_kg_acid_gas`. A loading
    spec is a column product spec on the bottoms composition (CO2 mole fraction expressed as a
    loading = x_CO2 / x_amine); use the column's existing spec machinery
    (`units/column/specs.py` after P1-03) — add a `component_ratio` spec kind there if none fits,
    and only there.
    Map: stage-N liquid → `lean_amine_out`, condenser vapour → `acid_gas_out`. `duty_W` = reboiler
    duty; `info` also carries `condenser_duty_W`, `stripping_steam_kg_per_h` (reboiler duty ÷
    water latent heat at the reboiler T via `thermo.phase_props` enthalpies, no `Chemical()`),
    `steam_kg_per_kg_acid_gas`, `stage_T_K`, `lean_co2_loading`, `lean_h2s_loading`.
- Edit: `src/ngdesign/units/mdea_absorber.py`, `mdea_regenerator.py` — accept `params["mode"]`
  (`"shortcut"` default, `"staged"`): `"staged"` delegates to the units above with the same
  ports, so the existing `amine_loop` / `mea_amine_loop` flowsheets switch by one param. The
  default path is untouched (byte-identical results for every existing test and golden).
- Create: `src/ngdesign/flowsheets/amine_loop_staged.py` — the MDEA `amine_loop` with
  `thermo="amine_ke"`, both units `mode="staged"`, 20 + 20 stages. Register it as bench case
  `amine_staged` in `scripts/bench_baseline.py` (reuse the P0-06 case plumbing).
- Tests:
  - `tests/units/test_amine_column.py`:
    (1) absorber: `MdeaAbsorber.example_case()` feed on 20 stages with `amine_ke` reaches an
    outlet CO2 ≤ the shortcut's spec (2 mol %) and the rich loading is within the shortcut's
    `[lean, equilibrium_max]` band; (2) the staged solve with 1 stage and Murphree 1.0 equals the
    shortcut unit's rich loading within 2 % (one equilibrium stage *is* the shortcut, up to the
    shortcut's spec-driven removal); (3) temperature bulge for 30 wt % MEA, 20 stages, the
    `mea_amine_loop` feed, is between 5 and 25 K (Kohl & Nielsen, *Gas Purification* 5th ed.,
    ch. 2, typical MEA absorber profiles); (4) component and energy balances close to 1e-6
    relative (`tests/property/test_unit_balances.py` style); (5) plain-cubic thermo raises
    `AmineColumnSpecError`; (6) regenerator: `lean_co2_loading` spec met within the column spec
    tolerance and `steam_kg_per_kg_acid_gas` for MDEA between 0.8 and 1.6 (Kohl & Nielsen ch. 2,
    MDEA reboiler steam 0.9–1.4 lb/lb typical); for MEA between 1.5 and 3.0.
  - `tests/e2e/test_amine_loop_staged.py`: the staged loop converges with the sequential-modular
    solver (same checks as `tests/e2e/test_amine_loop.py`: convergence, determinism, overall
    balances); lean loading at the absorber inlet equals the regenerator spec within the solver
    tolerance.
  - Existing amine tests, `tests/e2e/test_amine_loop.py`, `test_mea_amine_loop.py` PASS unchanged.

## Method
No new numerics: the column's inside-out / Naphtali–Sandholm machinery does the stage solve; the
amine package supplies reactive K-values and enthalpies with the heat of absorption. Cite Kohl &
Nielsen for the validation bands and Murphree (1925, Ind. Eng. Chem. 17, 747) for the stage
efficiency. Convergence failures surface as the column's `ColumnConvergenceError` with the stage
profile attached — never swallowed. All SI.

## Acceptance criteria
- [ ] `registry.available("unit")` includes `amine_absorber`, `amine_regenerator`
- [ ] All tests above PASS; every existing amine / column / e2e test PASS unchanged; `tests/e2e/test_slice.py` byte-identical
- [ ] `bench/baseline.json --check` passes with the new `amine_staged` case added and all existing cases unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Rate-based (mass-transfer) stages, packing hydraulics, lean/rich exchanger design, reclaimer,
degradation, the shortcut units' removal (they stay as the fast path).
