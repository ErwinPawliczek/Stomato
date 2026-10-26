# fixed_bed_tubular R2: multitubular packed-bed reactor with a shell-side coolant balance (co- or counter-current)

- **Family / package:** reactors, `src/ngdesign/units/reactors/`
- **Levels delivered:** R2 of row `fixed_bed_tubular`, from `planned` to `provisional`. This is the row's only level and its end state.
- **Depends on:** **pfr R2 merged.** It needs the public `plug_flow.integrate_plug_flow` with `HeatModel` and `ErgunBed` (pfr spec, R2 steps 4–5). Also U-R2 conventions and U-01d.
- **Wave/order:** after pfr R2.
- **Branch:** `u-lv/fixed_bed_tubular` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/reactors/fixed_bed_tubular.py` (new): adapter `FixedBedTubularR2` and the coolant `HeatModel` factory.
  - `tests/units/reactors/test_fixed_bed_tubular_r2.py` (new).
  - `data/validation_units/reactors/cases/fixed_bed_tubular.yaml` (new).
  - The `levels.R2` entry of row `fixed_bed_tubular` in `data/unit_models/reactors.yaml`, plus that row's `balance: mass_elements` key and its `notes` line.
- **Read-only imports:**
  - `ngdesign.units.reactors.plug_flow.integrate_plug_flow`, `HeatModel`, `ErgunBed`, `PlugFlowError`, `PlugFlowProfile`. These are the pfr spec's public API; verify the exact signatures on main when you start, because pfr R2 defines them.
  - `ngdesign.units.reactors._shared._solve_outlet_T`, `reaction_set_param` and `z_from`
  - `ngdesign.units._physics.kinetics.apply_extents` and `enthalpy_with_formation`
  - `scipy.optimize.brentq(f, a, b, xtol=..., maxiter=...)`
- **Current state:** `planned` only; there is no adapter. The ports are `inlet` (tube-side feed) and `outlet` (tube-side effluent). The coolant is described by params, not ports: the catalogue row has no coolant ports, and changing ports is a contract change, which is out of scope.

## Method

### Equations
Tube side: the pfr R2 equations 1–8 over the total reacting volume V_tot = n_t·A_c·L. The feed is split equally over n_t identical tubes, which is exact for identical tubes because every tube sees the same per-tube flow.

Shell side, per unit total reacting volume (Froment, Bischoff & De Wilde, *Chemical Reactor Analysis and Design*, 3rd ed., ch. 11, one-dimensional pseudo-homogeneous model with a coolant balance):
1. Heat into the process: q_V = U·a_w·(T_c − T), with a_w = 4/D_t.
2. Coolant temperature along V, with C_c = ṁ_c·c_p,c (W/K):
   - co-current: dT_c/dV = −q_V/C_c;
   - counter-current: dT_c/dV = +q_V/C_c, integrated in the tube direction while the coolant flows the other way.
3. Boundary conditions:
   - co-current: T_c(0) = T_c,in, an initial-value problem;
   - counter-current: T_c(V_tot) = T_c,in, a two-point boundary-value problem.

### Algorithm
1. Build `HeatModel(n_extra=1, y0_extra=(s,), q_V=..., d_extra=...)` from equations 1–2.
2. **Co-current:** s = T_c,in. Call `integrate_plug_flow(..., energy="heat_model", heat=model, ergun=bed or None)`.
3. **Counter-current, by shooting.** Unknown s = T_c(0); residual f(s) = T_c(V_tot; s) − T_c,in.
   - Initial bracket: [T_c,in − Δ, T_c,in + Δ] with Δ = |T_in − T_c,in| + 50 K.
   - If f has the same sign at both ends, widen Δ by ×2, at most 5 times. Otherwise raise `FixedBedError("counter-current shooting could not bracket")`.
   - Root: `brentq(f, lo, hi, xtol=1e-9, maxiter=100)`. A failure raises `FixedBedError`.
   - Each f(s) is one full `integrate_plug_flow` call. The integrator's own RHS cap of 20,000 applies per call.
   - Integration failures inside the bracket search propagate as `PlugFlowError`; they are not swallowed.
4. **Outlet.** n_out = `apply_extents(inlet flows, rset, ξ(V_tot))`, P_out = P(V_tot), Q = ∫q_V dV, and T_out = `_solve_outlet_T(thermo, z_from(n_out), Σn, P_out, T_in, enthalpy_with_formation(inlet) + Q)`. `duty_W` = Q.
5. **Info.**
   - `coolant_T_out_K`: T_c(V_tot) for co-current, s for counter-current;
   - `coolant_duty_W` = −Q;
   - `T_max_K` and `V_at_T_max_m3` (the hot spot);
   - `dP_Pa`, `extent_<id>_mol_s`, `T_closure_gap_K`;
   - `shooting_iterations` (counter-current only).

### Reduction to the lower level
With n_t = 1 and a coolant of infinite capacity (`coolant.mass_flow_kg_s` → ∞, here 1e12 kg/s), T_c stays constant at T_c,in. The result then equals pfr R2 with `thermal = {"coolant_T_K": T_c,in, "U_W_m2K": U}`. Same tube and bed, to 1e-8 relative on the outlet flows and T, and 1e-6 relative on Q. The residual coolant drift is about Q/C_c ≈ 1e-11 K.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `n_tubes` < 1; `tube_diameter_m`/`length_m`/`U_W_m2K` ≤ 0 | `FixedBedError` (ValueError) | the parameter name |
| `coolant.mass_flow_kg_s` or `coolant.cp_J_kgK` ≤ 0; `coolant.flow` not in {co, counter} | `FixedBedError` | the field name |
| counter-current bracket or `brentq` failure | `FixedBedError` | `shooting` |
| integration failure, phase, depletion or pressure floor | `PlugFlowError`, from pfr | as in the pfr spec |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| reaction_set | object/str | — | required | — | inline ReactionSet |
| n_tubes | integer | — | required | ≥ 1 | identical parallel tubes |
| tube_diameter_m | number | m | required | > 0 | tube inside diameter |
| length_m | number | m | required | > 0 | packed length |
| U_W_m2K | number | W/(m²·K) | required | > 0 | overall coefficient on the tube inside area |
| coolant | object | — | required | — | `{"mass_flow_kg_s": >0, "cp_J_kgK": >0, "T_in_K": >0, "flow": "co" \| "counter"}`; constant c_p (for example boiling water or molten salt at fixed c_p) |
| bed | object | — | absent | — | `{"particle_diameter_m", "voidage"}`; Ergun as in the pfr R2 spec |
| bulk_density_kg_m3 | number | kg/m³ | required for per-kg_cat rates | > 0 | catalyst bulk density |
| viscosity_Pa_s | number | Pa·s | from the flash | > 0 | Ergun override |
| reacting_phase | str | — | `"vapor"` | `"vapor"`, `"liquid"` | as in pfr |

```yaml
params:
  type: object
  required: [reaction_set, n_tubes, tube_diameter_m, length_m, U_W_m2K, coolant]
  properties:
    reaction_set: {description: inline ReactionSet, or a string id resolved against Flowsheet.reactions}
    n_tubes: {type: integer, description: identical parallel tubes}
    tube_diameter_m: {type: number, description: tube inside diameter, m}
    length_m: {type: number, description: packed tube length, m}
    U_W_m2K: {type: number, description: overall heat-transfer coefficient on the tube inside area, W/(m2 K)}
    coolant: {type: object, description: "{mass_flow_kg_s, cp_J_kgK, T_in_K, flow: co|counter}; constant-cp shell-side coolant"}
    bed: {type: object, description: "{particle_diameter_m, voidage}; Ergun pressure drop"}
    bulk_density_kg_m3: {type: number, description: catalyst bulk density, kg/m3}
    viscosity_Pa_s: {type: number, description: Ergun viscosity override, Pa s}
    reacting_phase: {type: string, enum: [vapor, liquid]}
```

## Outputs
- Port `outlet`: the tube-side effluent from the exact closure (algorithm step 4).
- `duty_W` = Q, the heat into the process from the coolant. `power_W` = 0.
- V0 on `mass_elements` and the formation basis at 1e-8.

## Tests
- **Closed-form, inert counter- and co-current exchanger** (`calc_fixed_bed_tubular.py`). Case: N2 tube side at 0.1 mol/s, 310 K, 2.0e5 Pa, `ideal-raoult`; empty reaction set; no bed; one tube, D_t 0.05 m, L 5.0 m; U = 5 W/(m²·K); coolant ṁ 1.0e-3 kg/s, c_p 4180 J/(kg·K), T_c,in 300 K. Using C_t = F·c_p,N2 with c_p = 29.2127371 J/(mol·K) (the package's N2 at 305 K), the ε-NTU closed forms (Incropera, *Fundamentals of Heat and Mass Transfer*, effectiveness-NTU relations for parallel and counter flow) give C_t = 2.92127371 W/K, C_c = 4.18 W/K, A = 0.785398163 m², NTU = 1.3442735, and:
  - **counter-current:** ε = 0.623650789, Q = 18.2185465 W, **T_t,out = 303.763492 K**, **T_c,out = 304.358504 K**;
  - **co-current:** ε = 0.528644626, Q = 15.4431565 W, **T_t,out = 304.713554 K**, **T_c,out = 303.694535 K**.

  Tolerance 2e-3 K: N2 c_p varies by less than 0.02 % over 300–310 K.
- **Identity:** the infinite-capacity coolant reproduces pfr R2 with a fixed coolant T (stated tolerances).
- **Reaction plus hot spot (consistency):** an exothermic first-order gas reaction with a counter-current coolant closes V0 at 1e-8. `T_max_K` > both T_in and T_out, and the shooting converges, with `shooting_iterations` reported.
- **Refusals:** one per refusal-table row. For the bracket failure, use a coolant `T_in_K` that makes f(s) one-signed after five expansions, for example a coolant c_p so small that T_c runs away and the integration refuses. Measure that input before writing the test.
- **V1:** Froment, Bischoff & De Wilde, 3rd ed., ch. 11, has the o-xylene → phthalic anhydride multitubular reactor. Its profiles are printed mainly as figures, and figure readings are not valid V1. If a table prints inlet conditions and the hot-spot temperature, use that with its page. Otherwise V1 gap: also search Fogler's non-isothermal packed-bed examples with a variable coolant temperature (printed final values).

## Steps (each about 40 minutes, each ending in a push)
1. **Co-current.** `fixed_bed_tubular.py`: `FixedBedError`, param parsing, the coolant `HeatModel`, the co-current solve, and the outlet closure. Tests: closed-form co-current, then the identity.
2. **Counter-current.** Shooting with bracket expansion and `brentq`. Tests: closed-form counter-current, the reaction/hot-spot V0 test, and the refusals.
3. **Catalogue.** YAML `levels.R2` (+ `balance: mass_elements`), `example_case` (the exothermic case), `cases/fixed_bed_tubular.yaml` (V1 or gap), harness write and `--audit`. Open the PR.

## Review checklist (for the orchestrator)
- No edit to `plug_flow.py`: the coolant enters only through `HeatModel`.
- Counter-current sign convention (dT_c/dV = +q_V/C_c) and BC at V_tot. The bracket rule and caps are as written; `brentq` uses xtol 1e-9.
- Equal feed split over tubes is implicit in V_tot, with G per tube in Ergun (the pfr owns this).
- Q sign: duty_W = heat into the process; `coolant_duty_W` = −Q.
- The ε-NTU expected values come from the closed-form script, not from the model.
