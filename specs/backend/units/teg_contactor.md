# teg_contactor R2: stage-wise TEG absorber on the Parrish-Won-Baltatu water activity (rating at N stages)

- **Family / package:** treating, `src/ngdesign/units/treating/`
- **Levels delivered:** R2, from `planned` to `provisional` (`end_state`)
- **Depends on:** U-R2 conventions, U-01d (#243).
- **Wave/order:** parallel-safe. **`teg_regen` R2 depends on this PR**, because it imports `teg_stagewise.countercurrent_march`. Dispatch regen after this merges.
- **Branch:** `u-lv/teg_contactor` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/treating/teg_stagewise.py` (new; the shared counter-current water-transfer march, owned here)
  - `src/ngdesign/units/treating/teg_contactor_r2.py` (new)
  - `tests/units/treating/test_teg_stagewise.py`, `tests/units/treating/test_teg_contactor_r2.py` (new)
  - `data/validation_units/treating/cases/teg_contactor.yaml` (new, only if a V1 case lands)
  - `data/unit_models/treating.yaml`: only `levels.R2` of row `teg_contactor`, plus its `notes` line
- **Read-only imports (verified on main):**
  - `ngdesign.units.teg_activity.activity_equilibrium_slope(T: float, P: float, x_water: float) -> float`, which returns m = γ_w(T, x_w)·Psat_H2O(T)/P, so that y* = m·x_w. The one owner of TEG-water equilibrium.
  - `ngdesign.units.teg_activity.water_activity_coefficient(T, x_water) -> float`, `water_activity(T, x_water) -> float`
  - `ngdesign.units.teg_contactor` helpers, read-only: `_water_content_lb_per_mmscf(y) -> float`; the module constants `LBMOL_PER_MMSCF` and `DEFAULT_WATER_OUT_LB_PER_MMSCF`
  - `Thermo.flash_pt(z, T, P, molar_flow) -> StreamState`
- **Current state:** R0 = `ngdesign.units.teg_contactor:TEGContactor`.
  - It takes an outlet water spec (lb/MMscf), removes that water, puts both outlets at (gas T, gas P) with `flash_pt`, and sets duty = the enthalpy difference.
  - Kremser stage count (`info["N_stages"]`) on the lean-end activity slope.
  - Ports: `gas_in`, `lean_teg_in` → `gas_out`, `rich_teg_out`. No V1.

## Method
### Equations
Counter-current equilibrium stages j = 1..N, top to bottom, isothermal at T = `gas_in.T`, P = `gas_in.P` (the R0 convention: GPSA contactor practice treats the column as at the gas temperature). Water is the only transferring species; hydrocarbon co-absorption and TEG losses are neglected, as in R0.
- Mole ratios on the solute-free bases: gas `Y = n_w/G` with dry gas G = (1 − y_in)·F_gas; liquid `X = n_w/S` with TEG S = n_TEG of the lean.
- 1. Stage balance: `G·(Y_{j+1} − Y_j) = S·(X_j − X_{j−1})`, with X_0 = X_lean and Y_{N+1} = Y_in.
- 2. Stage equilibrium: `y_j = m(T, P, x_j)·x_j`, with `y = Y/(1 + Y)`, `x = X/(1 + X)`, and m from `activity_equilibrium_slope` (Parrish, Won & Baltatu 1986, as parameterized in Filep et al. 2022, eqs. 12–17).

y*(x) = m(x)·x is strictly increasing in x on (0, 1) over the fitted range. This was verified numerically while writing the spec, and the implementer asserts it on a 1000-point grid in a test.

### Algorithm: `teg_stagewise.countercurrent_march`
```
countercurrent_march(G, S, X_top_in, Y_bottom_in, n_stages, x_of_y) -> (Y[0..N], X[1..N])
```
Here `x_of_y(Y) -> X` is the stage equilibrium inverse in ratio space.
1. Unknown: Y_1, the gas leaving the top stage.
2. Shoot downwards. For a trial Y_1 and j = 1..N: X_j = x_of_y(Y_j), then Y_{j+1} = Y_j + (S/G)·(X_j − X_{j−1}). If any Y_{j+1} < 0, return −1.0 as the residual sentinel (an overshoot).
3. Residual: r(Y_1) = Y_{N+1}(Y_1) − Y_bottom_in.
4. Bracket by a log-spaced scan of Y_1 over [1e-14, 1e6] (400 points). Exactly one sign change is required.
   - No sign change: raise `TEGStageError("no bracket")`.
   - More than one: raise `TEGStageError("multiple roots")`, listing them.
5. Bisection on the bracket to |Δ ln Y_1| < 1e-14 or 300 iterations. At the cap, raise `TEGStageError("bisection cap")`.

Never use a fixed bracket such as [Y*(X_lean), Y_in]. While this spec was written, a bottom-up march with a fixed bracket silently returned a wrong root for the stripping case (N = 3); the log scan found the single true root.

`x_of_y` for TEG: invert `y = m(T, P, x)·x` by bisection on x in [0, 1 − 1e-12], 200 iterations, then convert y↔Y and x↔X. If Y exceeds the pure-water limit (y ≥ 1), return +inf for the shooter. If the cap is hit without |Δx| < 1e-15, raise `TEGStageError`.

### Algorithm: `TEGContactorR2.solve`
1. Validate `n_stages` (int ≥ 1). The lean must carry TEG > 0; the gas must carry H2O > 0.
2. Compute G, S, Y_in, X_lean; run the march with the TEG `x_of_y`.
3. Water removed: `ΔW = G·(Y_in − Y_1)`. This is ≥ 0 for absorption; if it is negative (the lean is wetter than equilibrium with the gas), allow it and report it (desorption is physical).
4. Outlets, both at (T_gas, P_gas) as in R0:
   - `gas_out = flash_pt(gas composition with water ΔW removed, T, P, F_gas − ΔW)`;
   - `rich_teg_out = flash_pt(lean composition with ΔW added, T, P, F_lean + ΔW)`.
5. `duty_W = ΣH_out − ΣH_in`, using the actual inlet states (the R0 convention: heat of absorption and the temperature equalisation reported through the duty).
6. `info`:
   - `n_stages`, `outlet_water_lb_per_mmscf` (via R0's `_water_content_lb_per_mmscf`), `water_removed_mol_s`, `equilibrium_floor_lb_per_mmscf` (y* at the lean), `rich_x_water`;
   - per stage: `stage_{j}_y_H2O`, `stage_{j}_x_H2O`;
   - `activity_extrapolated` (1.0 if T is outside 300–380 K, the owner correlation's fitted range, as the R0 regen flags it).

### Reduction to the lower level
None exact: R0 is spec-driven (outlet water given) and R2 is rating (N given). Two relations are tested instead:
- **Kremser identity of the march (exact):** with an injected linear equilibrium Y* = m·X, `countercurrent_march` must reproduce the Kremser absorption solution in ratio space, `(Y_in − Y_1)/(Y_in − m·X_0) = (A^{N+1} − A)/(A^{N+1} − 1)` with A = S/(m·G), to 1e-12 relative.
- **R0 round trip (inequality, not identity):** for R0's example, R2 at N = ceil(R0 `info["N_stages"]`) gives an outlet water content. Report it; assert only that it is finite and below the inlet. The activity line is curved, so R0's lean-end-slope Kremser N is not exact.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `n_stages` missing, non-integer or < 1 | `TEGContactorR2Error(ValueError)` (new) | `n_stages` |
| lean without TEG | `TEGContactorR2Error` | `TEG` |
| gas without H2O | `TEGContactorR2Error` | `H2O` |
| unknown param key | `TEGContactorR2Error` | `unknown` |
| march bracket or bisection failure | `TEGStageError(ValueError)` (new, in `teg_stagewise.py`) | `bracket` / `multiple roots` / `cap` |

## Params
```yaml
params:
  type: object
  required: [n_stages]
  additionalProperties: false
  properties:
    n_stages: {type: integer, minimum: 1, description: equilibrium stages (isothermal at the gas inlet T and P)}
```

## Outputs
- `gas_out` and `rich_teg_out` at (gas T, gas P).
- `duty_W` = the enthalpy difference; `power_W` = 0.
- `info` as listed in the Algorithm.

## Tests (numbers from `calc_teg_contactor.py`: own IAPWS-IF97 Psat and own Parrish γ, cross-checked against `chemicals.Psat_IAPWS` and `teg_activity` to 1e-15)
- **Closed-form march, R0 example basis:** T = 303.15 K, P = 7.1 MPa; gas 100 mol/s with y_H2O = 0.0005 (G = 99.95, Y_in = 5.0025e-4); lean 0.2 mol/s at x_H2O = 0.015 (S = 0.197, X_0 = 0.015228426).
  - Expected (rel 1e-7; the bisection floor is far below that):

    | N | y_H2O out | gas_out flow (mol/s) | water removed (mol/s) | rich x_H2O |
    |---|---|---|---|---|
    | 1 | 7.17911038e-05 | 99.957176036 | 0.042823964 | 0.188712692 |
    | 2 | 1.58095229e-05 | 99.9515801868 | 0.0484198132 | 0.206987569 |
    | 3 | 6.90613904e-06 | 99.9506902734 | 0.0493097266 | 0.209818234 |
    | 4 | 5.41853074e-06 | 99.9505415851 | 0.0494584149 | 0.210289218 |

  - Lean-end floor y* = 5.115774429894135e-06; outlet y must stay above it.
  - Psat_H2O(303.15 K) = 4246.688340548065 Pa; γ_w(303.15, 0.015) = 0.5702011471768885.
- **Kremser identity** (`test_teg_stagewise.py`): m = 0.001, same G/S/X_0/Y_in, A = 1.97099. Y_1 = 1.78481225796e-4 (N=1), 4.86491069546e-5 (N=3), 1.9339588953e-5 (N=6), matching closed-form Kremser to ≤ 4e-16 relative.
- **Monotonicity:** y*(x) increasing on a 1000-point grid at 303.15 K and 7.1 MPa (guards the bisection assumption).
- **V0:** total moles conserved exactly (water moves between streams), and the energy closes by the duty definition.
- **Refusals:** one per row of the table, including a constructed multiple-root case for `TEGStageError` (inject a non-monotone `x_of_y` in a unit test of the march).
- **V1 candidates:** GPSA Engineering Data Book Sect. 20 (glycol dehydration) works a contactor example on McCabe-Thiele / Kremser charts. Use it only if the printed inputs (gas T, P, water in, lean wt%, circulation, stages) and printed outlet water are all visible on the page; otherwise record a V1 gap. Never read values off a chart and present them as printed numbers. A chart read must be labelled as such in `assessed`.

## Steps
1. **`teg_stagewise.py`:** the march, the bracket scan and bisection, `TEGStageError`, the Kremser identity tests and the multiple-root refusal test (≈40 min). Push and open the PR.
2. **`teg_contactor_r2.py`:** the TEG `x_of_y`, the adapter, the outlets and duty, the info, the closed-form table test, the monotonicity test and the refusals (≈40 min). Push.
3. **`example_case`** (R0's feeds plus `{"n_stages": 3}`), catalogue flip, docs and gates (≈25 min). Row note: "stage-wise isothermal water absorption on the Parrish-Won-Baltatu activity line (rating at N stages)". Push.

## Review checklist
- Ratio bases: G is the dry gas and S is the TEG moles only.
- Equilibrium uses `activity_equilibrium_slope`, the owner, never a re-derived γ or Psat.
- The log-scan bracket requires exactly one sign change.
- The overshoot sentinel is used.
- Outlets are at gas (T, P); duty uses the actual inlet enthalpies.
- `activity_extrapolated` is flagged.
- The Kremser identity is at 1e-12.
