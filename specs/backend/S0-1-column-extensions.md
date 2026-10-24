# S0-1: Column extensions — pumparounds, coupled side strippers, steam and free water, draw and temperature specs

- **Phase:** Unit catalogue round 2 (slice S0, crude refining), step 1 of the plan's Round 2: "the column extensions first" (`docs/unit-catalogue-plan.md` §5).
- **Depends on:** P1-11 (merged), U-01/U-01b/U-01c (merged), round 1 (merged).
- **Packages you may edit:** `ngdesign.units.column` (`spec.py`, `specs.py`, `inside_out.py`, `naphtali_sandholm.py`, new modules inside the package); `data/unit_models/column.yaml` (the `column_extensions` row only); `data/validation_units/column/` (append cases); `tests/units/column/` (new files only), generated `docs/units*`.
- **Never edit:** `contracts/`, `thermo/`, `amine/`, `solver/`, `scripts/validate_units.py`, `units/catalogue.py`, `units/levels.py`, the refining package, `tests/property/`.
- **GitHub issue:** #235
- **Contract change:** no. Everything is new `params` keys on the existing column unit, plus extra internal products reported in the result; the column's registered ports stay `feed` → `distillate`, `bottoms`, `side_draw`.
- **Benchmark delta expected:** none. `column` stays at 6,508 flash-equivalents, and `slice`, `slice_spec`, `recycle_bench`, `amine_loop` and `mea_amine_loop` stay identical. The byte-identical dispatch golden (`tests/units/test_unit_catalogue.py`) must pass unchanged: every new key is optional and absent means today's code path.

## Goal
A crude tower is a MESH column plus four things the package lacks today (survey of `units/column/`, 2026-10-24): pumparounds, side strippers coupled to the main column, stripping steam with free-water removal at the condenser, and the specs refiners use (a side product's rate, a stage temperature). Build them as general column features, not crude-specific code, so S0-3 (atmospheric and vacuum columns at R2) only has to configure them.

## Features (each optional; absent = today's behaviour, byte-identical)
1. **Pumparounds:** `params["pumparounds"] = [{draw_stage, return_stage, flow_mol_s, duty_W | return_T_K}]`.
   - Liquid leaves `draw_stage`, is cooled externally by `duty_W` (negative = heat removed) or to `return_T_K`, and re-enters `return_stage` (`return_stage < draw_stage`, i.e. above) as a subcooled liquid feed.
   - In MESH terms: a liquid side draw on the draw stage, and a feed on the return stage at the cooled enthalpy.
   - Report each pumparound's duty, draw T and return T in info. A `flow_mol_s` or duty may instead be the tear of a spec (feature 4).
2. **Coupled side strippers:** `params["side_strippers"] = [{draw_stage, return_stage, n_stages, steam: {flow_mol_s, T_K, P_Pa} | reboiler_duty_W, product_rate_mol_s}]`.
   - Liquid drawn from the main column feeds the top of an `n_stages` stripper section.
   - Stripping steam, or a reboiler, enters at the bottom of the stripper.
   - The stripper overhead vapour returns to `return_stage` of the main column; the stripper bottoms is a product.
   - Solve the coupling one of two ways, and say which in the module docstring:
     - simultaneously, by augmenting the MESH system with the stripper stages; or
     - as a tear on the vapour return, using the existing Broyden spec machinery.
   - Converged means every stage and the coupling meet the current non-reactive gates, and the boundary balances close at 1e-8.
3. **Steam and free water:**
   - Stripping steam enters as an ordinary extra feed (multiple feeds already exist).
   - Add `params["condenser_water_decant"] = true`: water that the package puts in an aqueous liquid phase at the condenser leaves as a separate internal product, `water_decant`. Hydrocarbon reflux and distillate then carry only the hydrocarbon liquid.
   - If the package returns no aqueous phase there, the decant is zero-flow (not an error).
4. **Specs:** add to `_SPEC_KEYS`:
   - `draw_rate`: the molar rate of a named side draw or stripper product;
   - `stage_temperature`: T on a named stage;
   - `pumparound_duty` and `pumparound_return_T`.

   Each spec pairs with a named tear (`flow_mol_s` of a draw, a pumparound flow or duty, the reflux or boilup), and the spec count must still equal the tear count; refuse otherwise, naming both lists.
5. **Products:** the column result's info reports every internal product: side draws, stripper bottoms, water decant, pumparound loops. `Column.solve` keeps returning the three registered outlets. A later adapter (S0-3) maps the full product set to its own catalogue ports. Expose one engine function, for example `solve_column_full(...) -> ColumnProducts`, that S0-3 will call.

## Acceptance
- **Identity tests:** the new features reduce exactly to today's column.
  - A pumparound with `duty_W = 0` and draw = return is the column without it (1e-10).
  - A side stripper with `n_stages = 0` is a plain liquid side draw.
  - A zero-flow steam feed changes nothing.
  - `condenser_water_decant` on a water-free feed gives a zero decant and an unchanged column.
- **Coupled case** (pseudo-component feed, for example the A-01 Bagajewicz & Ji slate at a reduced pseudo count chosen for speed):
  - a 20+ stage main column with one pumparound, two side strippers on steam, and bottom steam;
  - converges with mass, component and energy closure at 1e-8 on the whole unit (main + strippers + pumparound coolers);
  - deterministic (bit-identical rerun);
  - wall time stated, and every test under 60 s on a developer machine. No timeout raises: if a solve is slow, profile it and fix the cause.
- **Spec tests:** a `draw_rate` spec hits its target to 1e-8 relative, and a `stage_temperature` spec to 1e-6 K. An unreachable spec refuses with a typed error naming the spec.
- **Catalogue:** flip the `column_extensions` row's R2 level to `provisional`, with an adapter that exposes the row's ports (U-01c enforces this). Record a V1 gap or a cited printed example (Kister, Distillation Design; Watkins, Petroleum Refinery Distillation, if open, with printed inputs and results only). V0 stays clean.
- **Gates:** ruff, ruff format, `mypy src tests` (strict), lint-imports, `scripts/bench_baseline.py --check` (identical counts), harness `--audit`. The bench dispatch golden passes unchanged. GitHub CI green.

## Out of scope
Crude-specific configuration and the S0 reference match (S0-3); the vacuum column's wash zone and overflash (S0-3); column hydraulics (`column_internals`); three-phase stages beyond the condenser decant; reactive stages.
