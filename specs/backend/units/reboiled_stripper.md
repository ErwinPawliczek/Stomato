# reboiled_stripper R2: one-tear MESH stripper (kettle only) via the column API

- **Family / package:** column, `src/ngdesign/units/column_shortcut/`
- **Levels delivered:** R2, from `planned` to `provisional`. R3 (rate-based) stays `planned`.
- **Depends on:** U-R2 conventions, U-01d (#243). Calls the public column API only; edits nothing in `src/ngdesign/units/column/`.
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/reboiled_stripper` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/column_shortcut/reboiled_stripper_r2.py` (new)
  - `tests/units/column_shortcut/test_reboiled_stripper_r2.py` (new)
  - `data/validation_units/column/cases/reboiled_stripper.yaml` (new, only if a V1 case lands)
  - `data/unit_models/column.yaml`: only `levels.R2` of row `reboiled_stripper`, plus its `notes` line
- **Read-only imports (verified on main, 2026-10-25):**
  - `ngdesign.units.column.Column` — `Column().solve(inlets, params, thermo) -> UnitResult`; outlets `distillate`, `bottoms`, `side_draw`; info `reboiler_duty_W`, `boilup_ratio`, `distillate_mol_s`, `bottoms_mol_s`, `stage_{j}_*`
  - `ngdesign.units.column.ColumnSpecError`, `ngdesign.units.column.ColumnConvergenceError`
  - `ngdesign.units.column.spec._SPEC_TOL` (read-only constant = 5e-3, used in test tolerances only)
- **Current state:** R0 = `ngdesign.units.column_shortcut.stripper:ReboiledStripper` (Kremser stripping side, params `N`, `vapour_flow`, `k_overrides`). Ports: inlet `feed` (liquid to the top stage); outlets `overhead`, `bottoms`. V1 `V1-kremser-stripper-seader98`.

## Method
### Equations
MESH equilibrium-stage column (Boston & Sullivan 1974 inside-out, Naphtali & Sandholm 1971 fallback, as implemented in `ngdesign.units.column`):
- `n_stages` stages, top to bottom; the feed enters stage 1;
- no condenser; the kettle reboiler is stage N;
- one tear (the boilup V_N), driven by exactly one spec through the column's bounded secant (P1-09/P1-10).

`overhead` = stage-1 vapour (`distillate`); `bottoms` = kettle liquid.

### Algorithm
1. Validate `n_stages` (int ≥ 2), `pressure_profile` (default `feed.P`), and `spec`. `spec` is a one-key dict from the allowed set `{boilup_ratio, bottoms_rate, distillate_rate, component_recovery}`.
2. `Column().solve({"feed": feed}, {"n_stages": N, "condenser": "none", "reboiler": "kettle", "pressure_profile": p, "feed_stage": 1, "specs": spec}, thermo)`.
3. Map the outlets: `overhead = distillate`, `bottoms = bottoms`. `duty_W = result.duty_W`, the physical reboiler duty; the column defines it by the exact overall balance, so V0 closes by construction.
4. `info`:
   - copy `reboiler_duty_W`, `boilup_ratio`, `distillate_mol_s`, `bottoms_mol_s` and all `stage_{j}_*` keys;
   - add `spec_name` (as a float code: 1 boilup_ratio, 2 bottoms_rate, 3 distillate_rate, 4 component_recovery) and `spec_achieved`, the measured value of the spec quantity from the outlets.

The column's tolerances and bounded budgets apply; this adapter adds no iteration.

### Reduction to the lower level
None exact (Kremser vs MESH). The identity is to the column row: the adapter output equals `Column().solve` with the mapped params, bit-for-bit.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `n_stages` missing, non-integer or < 2 | `ReboiledStripperR2Error(ValueError)` (new) | `n_stages` |
| `spec` missing, not exactly one key, or key outside the allowed set | `ReboiledStripperR2Error` | `spec` |
| `spec = {"reboiler_duty_W": ...}` | `ReboiledStripperR2Error` | `reboiler_duty_W` and `singular` (see the note below) |
| `pressure_profile` invalid (length or ≤ 0) | `ReboiledStripperR2Error` | `pressure_profile` |
| feed molar flow ≤ 0 | `ReboiledStripperR2Error` | `feed` |
| unknown param key | `ReboiledStripperR2Error` | `unknown` |
| column failure | re-raised `ColumnConvergenceError` / `ColumnSpecError` unchanged | — |

**Note on `reboiler_duty_W`:** it is a legal column spec key, but measured on main (2026-10-25) a kettle-only stripper given `{"reboiler_duty_W": 1e6}` fails with `ColumnConvergenceError: singular Newton system in column solver` for every case tried:
- nC4/nC5 0.3/0.7 at 330 K;
- nC4/nC5 0.02/0.98;
- the near-pure and pure nC5 limits at 5 bar.

The R2 params schema therefore excludes it, and the adapter refuses it with a message pointing at the column core. This is reported to the orchestrator as a core column defect; the adapter must not work around it.

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `n_stages` | integer | — | required | ≥ 2 | stages including the kettle (stage N) |
| `pressure_profile` | number or array | Pa abs | default `feed.P` | > 0 | stage pressures |
| `spec` | object, exactly one key | — | required | see below | the column's single degree of freedom |

The allowed `spec` keys:
- `boilup_ratio`: number > 0;
- `bottoms_rate`: mol/s, number > 0;
- `distillate_rate`: mol/s, number > 0;
- `component_recovery`: `{component, value, product}`, the column's format.

```yaml
params:
  type: object
  required: [n_stages, spec]
  additionalProperties: false
  properties:
    n_stages: {type: integer, minimum: 2, description: stages including the kettle reboiler (stage N); feed on stage 1}
    pressure_profile:
      description: stage pressures, Pa abs; default feed P
      oneOf:
      - {type: number, exclusiveMinimum: 0}
      - {type: array, items: {type: number, exclusiveMinimum: 0}}
    spec:
      type: object
      description: exactly one of boilup_ratio, bottoms_rate (mol/s), distillate_rate (mol/s), component_recovery ({component, value, product})
      minProperties: 1
      maxProperties: 1
```

## Outputs
- `overhead`: stage-1 vapour. `bottoms`: kettle liquid.
- `duty_W`: the reboiler duty (W, > 0). `power_W` = 0.
- `info`: as in the Algorithm, plus `spec_achieved`.

## Tests
- **Closed-form (material identity of a rate spec):**
  - Case: feed nC4/nC5 = 0.3/0.7, 330 K, 5 bar, 100 mol/s (subcooled liquid, VF 0), N = 4, `spec = {"bottoms_rate": 60.0}`. The total balance is exact: `overhead + bottoms = 100` (rel 1e-8). `bottoms` = 60 holds only to the column's documented spec gate `_SPEC_TOL = 5e-3`.
  - **Measured on main:** B = 60.09258777156105 (rel error 1.54e-3, inside 5e-3); D = 39.90741222843895; D + B = 100.0 exactly.
  - The test asserts `abs(B − 60)/60 < _SPEC_TOL`, imported from the column, never a looser literal. The measured value goes in the comment.
- **Closed-form (phase-state identity):** the kettle `bottoms` is saturated liquid and the stage-1 `overhead` saturated vapour, both independent of the column.
  - `thermo.bubble_point(bottoms.composition, P=P).T` equals the kettle stage T (abs 1e-4 K);
  - `thermo.dew_point(overhead.composition, P=P).T` equals the stage-1 T (abs 1e-4 K).
  - Measured on main (script `calc_reboiled_stripper_phase.py`):

    | spec | kettle T (K) | bubble T (K) | Δ (K) | top T (K) | dew T (K) | Δ (K) |
    |---|---|---|---|---|---|---|
    | `boilup_ratio` 0.5 | 351.7078018 | 351.7078015 | −3.5e-7 | 346.1163468 | 346.1163432 | −3.7e-6 |
    | `bottoms_rate` 60 | 355.9375316 | 355.9375307 | −9.6e-7 | 346.978996 | 346.978996 | −1.2e-8 |

  - Achieved boilup ratio 0.50168, inside 5e-3.
- **Identity to the column row:** for the R0 `example_case` feed, the adapter's outlets `==` a direct `Column().solve` with the mapped params.
- **Spec-achieved tests:** for each allowed spec key, `spec_achieved` is within `_SPEC_TOL` (relative) of the target.
  - Measured on main for the nC4/nC5 case: boilup 0.501683 vs 0.5; distillate 39.9074 vs 40; nC4 recovery 0.898828 vs 0.9.
  - All are inside 5e-3, and all run in under 6 s.
- **Refusals:** one per row of the table, including the `reboiler_duty_W` refusal (it must not call the column).
- **V1 candidates:** V1 gap unless a printed rigorous reboiled-stripper example is found, with its inputs and printed product flows or duties. Search:
  - Seader, Henley & Roper 3rd ed., the rigorous-methods chapter;
  - Kister, *Distillation Design* (1992), the stripper examples.
  - Never reconstruct.

## Steps
1. **Adapter, identity and refusals (≈35 min).** `ReboiledStripperR2` with `inlet_ports = ("feed",)`, `outlet_ports = ("overhead", "bottoms")`, and `example_case` = R0's feed plus `{"n_stages": 4, "spec": {"boilup_ratio": 0.5}}`. Push and open the PR.
2. **Closed-form, spec-achieved and phase-state tests (≈35 min).** Push.
3. **Catalogue flip, docs and gates (≈30 min).** `adapter: ngdesign.units.column_shortcut.reboiled_stripper_r2:ReboiledStripperR2`, the note "one-tear MESH (kettle only) via the column API; specs met to the column's _SPEC_TOL", and the V1 gap in `notes`. Push.

## Review checklist
- The adapter passes `condenser="none"`, `reboiler="kettle"`, `feed_stage=1`, and exactly one spec.
- `reboiler_duty_W` is refused before any column call, and the message names the core defect.
- Spec tolerances import `_SPEC_TOL`; no literal tolerance looser than it.
- The phase-state checks use thermo bubble/dew points, not column outputs.
- No `except` around the column call.
