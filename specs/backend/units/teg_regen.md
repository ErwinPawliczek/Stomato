# teg_regen R2: boiling-line reboiler plus an N-stage stripping-gas (Stahl) section

- **Family / package:** treating, `src/ngdesign/units/treating/`
- **Levels delivered:** R2, from `planned` to `provisional` (`end_state`)
- **Depends on:** U-R2 conventions, U-01d (#243), and **`teg_contactor` R2 merged** (imports `teg_stagewise.countercurrent_march` and `TEGStageError`).
- **Wave/order:** after `teg_contactor`.
- **Branch:** `u-lv/teg_regen` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/treating/teg_regen_r2.py` (new)
  - `tests/units/treating/test_teg_regen_r2.py` (new)
  - `data/validation_units/treating/cases/teg_regen.yaml` (new, only if a V1 case lands)
  - `data/unit_models/treating.yaml`: only `levels.R2` of row `teg_regen`, plus its `notes` line
- **Read-only imports (verified on main, except the first, which arrives with teg_contactor R2):**
  - `ngdesign.units.treating.teg_stagewise.countercurrent_march(G, S, X_top_in, Y_bottom_in, n_stages, x_of_y)`, `TEGStageError`
  - `ngdesign.units.treating.teg_regen.TEGRegen` (R0), `TEGRegenError`, `_lean_water_mole_fraction(T: float, P: float) -> float` (the R0 boiling-line solve), `DEFAULT_T_REBOILER = 477.15`, `DEFAULT_P = 101325.0`, `_PARRISH_T_MIN, _PARRISH_T_MAX = 300.0, 380.0`
  - `ngdesign.units.teg_activity.activity_equilibrium_slope(T, P, x_water) -> float`
  - `Thermo.flash_pt`
- **Current state:** R0 = `ngdesign.units.treating.teg_regen:TEGRegen`.
  - Lean purity from the boiling line at (T_reboiler, P); both outlets at (T_reb, P); duty = enthalpy difference.
  - A positive stripping-gas flow is **refused**: no citable GPSA enhancement correlation.
  - V1 `V1201-teg-regen-gpsa`: measured 99.27 wt% vs the GPSA read of 98.8 wt%, assessed. The Parrish correlation is extrapolated at 477 K.
  - Ports: `rich_in`, `stripping_gas_in` (optional) → `water_out`, `lean_out`.

## Method
R2 replaces R0's stripping-gas refusal with a first-principles staged model. The lean leaving the reboiler, at the boiling-line water fraction x_reb (R0's own solve), flows down an N-stage stripping column (the Stahl column) counter-current to the stripping gas, isothermal at (T_reb, P). Each stage is at water-activity equilibrium. The enhancement in lean purity is computed, not read from a chart.

### Equations
- Reboiler: `x_reb` solves `m(T_reb, P, x)·x = 1` (R0, `_lean_water_mole_fraction`); X_0 = x_reb/(1 − x_reb).
- Stahl stages j = 1..N, top to bottom:
  1. Balance `S·(X_{j−1} − X_j) = G·(Y_j − Y_{j+1})`. This is the same equation the march solves, written for stripping.
  2. Equilibrium `y_j = m(T_reb, P, x_j)·x_j`.
  - S = the TEG molar flow of `rich_in`; G = the non-water molar flow of `stripping_gas_in`; Y_{N+1} = the gas's own water ratio (0 for dry gas).
- Lean outlet: X_N on TEG S. Overhead: the rich feed's water minus the lean water, plus all absorbed lights, plus all the stripping gas (dry plus its water). Everything leaves through `water_out` (no condenser, as in R0).

### Algorithm
1. As R0: validate T_reboiler and P, refuse if P ≥ Psat_H2O(T_reb), and compute x_reb.
2. If `stripping_gas_in` is absent or has zero flow, or `n_stages == 0`, the lean is at x_reb and the result is R0's exactly. Delegate to `TEGRegen().solve` and return its result with the R2 info added.
3. Otherwise:
   - refuse a stripping gas carrying TEG;
   - compute G and Y_{N+1};
   - call `countercurrent_march(G, S, X_0, Y_{N+1}, n_stages, x_of_y)`, with `x_of_y` the TEG equilibrium inverse at (T_reb, P), the same construction as teg_contactor R2;
   - X_lean = X_N;
   - cap: if X_lean > X_0 (no stripping possible), refuse; this cannot happen for dry gas.
4. Outlets at (T_reb, P), as R0:
   - `lean_out = flash_pt({TEG, H2O at X_lean}, T_reb, P, S·(1 + X_lean))`;
   - `water_out = flash_pt(overhead composition, T_reb, P, total)`, where the overhead = rich water − S·X_lean, plus lights, plus the stripping gas with its water.
5. `duty_W = ΣH_out − ΣH_in` (actual inlet states).
6. `info`:
   - R0's keys;
   - `n_stages`, `stripping_gas_mol_s`, `lean_teg_mass_fraction` (R2 value), `lean_teg_mass_fraction_boiling_line` (R0 value), `purity_enhancement_wt_pct`, `stage_{j}_x_H2O`, `stage_{j}_y_H2O`;
   - `activity_extrapolated` (1.0 at a 477 K reboiler, as R0).

### Reduction to the lower level
Exact: with zero stripping gas (or N = 0), R2 delegates to R0, so the result is R0's, field for field. The identity test also checks the march itself: as G → 0 with N ≥ 1, X_lean → X_0. At G = 1e-9 mol/s, X_lean matches X_0 to rel 1e-6. The G → 0 limit is singular in the march, so the delegation path, not the march, carries exact zero.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `n_stages` non-integer or < 0 | `TEGRegenError` (reuse R0's error class) | `n_stages` |
| stripping gas carries TEG | `TEGRegenError` | `stripping gas` |
| P ≥ Psat_H2O(T_reb) | `TEGRegenError` (R0's own refusal, via R0's solve) | `no boiling` |
| march failure | `TEGStageError` (from teg_stagewise, unchanged) | — |
| unknown param key | `TEGRegenError` | `unknown` |

## Params
```yaml
params:
  type: object
  additionalProperties: false
  properties:
    T_reboiler: {type: number, description: reboiler temperature (K), default 477.15}
    P: {type: number, description: regenerator pressure (Pa abs), default 101325}
    n_stages: {type: integer, minimum: 0, description: stripping-gas (Stahl) equilibrium stages below the reboiler; 0 = R0 boiling-line purity, default 2}
```

## Outputs
- `lean_out` and `water_out` at (T_reb, P).
- `duty_W` = the enthalpy difference; `power_W` = 0.
- `info` as listed in the Algorithm.

## Tests (numbers from `calc_teg_regen.py`: own IF97 Psat and own Parrish γ; the top-down log-scan shooting found a single root in every case)
- **Boiling line (R0 identity), T_reb = 477.15 K, P = 101325 Pa:** Psat = 1689056.3499963796 Pa; x_reb = 0.058674712754515884 (99.25779284649195 wt% TEG on the databank MWs TEG 150.17296, H2O 18.01528); γ at x_reb = 1.0224015555612633, extrapolated.
- **Stahl section,** S = 82.0 mol/s TEG, dry stripping gas, Y_{N+1} = 0. Expected (rel 1e-7):

  | N | G (mol/s) | Y_1 | lean x_H2O | lean TEG wt% |
  |---|---|---|---|---|
  | 1 | 2.0 | 1.20119822 | 0.0319781273 | 99.6052706 |
  | 2 | 2.0 | 1.62378146 | 0.0222225357 | 99.7280930 |
  | 3 | 2.0 | 1.82457116 | 0.0175179409 | 99.7865581 |
  | 4 | 2.0 | 1.93751541 | 0.0148516561 | 99.8194748 |
  | 2 | 5.0 | 0.826941334 | 0.0117686245 | 99.8573419 |

  The test drives the march directly with the TEG `x_of_y` at these inputs. The unit-level test builds `rich_in` with S = 82 mol/s TEG and asserts the lean wt%. The wt% column is on the databank MWs (TEG 150.17296, H2O 18.01528; verified).
- **Physics direction:** lean purity increases strictly with N at fixed G, and with G at fixed N (from the table).
- **Identity:** zero stripping gas gives an R0-identical result (`==`).
- **V0:** total moles and energy close.
- **Refusals:** one per row of the table.
- **V1:** keep R0's GPSA Sect. 20 case.
  - The stripping-gas enhancement chart is not available in citable numeric form (R0's notes). V1 gap for the enhancement: search the GPSA EDB Sect. 20 worked regeneration example, and Moshfeghian (Campbell Tip of the Month, May 2013). The latter prints simulation results, which are not a V1 source.
  - The R0 boiling-line miss (99.27 vs 98.8 wt%, Parrish extrapolated at 477 K) carries over, and is reported in `assessed`.

## Steps
1. **R2 module:** R0 delegation for the zero-gas path, the march call with the TEG `x_of_y`, outlets, duty, info, and the identity and refusal tests (≈40 min). Push and open the PR.
2. **Closed-form table tests, monotonicity tests,** `example_case` (R0's feeds plus `stripping_gas_in` = 2 mol/s dry C1 at 477.15 K and 1.5e5 Pa, `n_stages` 2), catalogue flip, docs and gates (≈40 min). Row note: "boiling-line reboiler + N-stage stripping-gas section on the Parrish activity line (extrapolated above 380 K; flagged)". Push.

## Review checklist
- x_reb comes from R0's `_lean_water_mole_fraction`, the one owner.
- The march is imported from `teg_stagewise`, never copied.
- G excludes the gas's water, and Y_{N+1} is its water ratio.
- The overhead includes all the stripping gas.
- The zero-gas path delegates to R0.
- `activity_extrapolated` is reported.
- The wt% basis uses databank MWs.
