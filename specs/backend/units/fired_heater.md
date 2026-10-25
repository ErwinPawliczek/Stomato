# fired_heater R1: Lobo-Evans radiant section plus a rated convection section, with fuel and flue-gas balance

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional` (`end_state: true` stays on R1).
- **Depends on:** the U-R2 conventions and U-01d (#243). No transport properties are needed, so T-PP is not required. **Parallel-safe now.**
- **Branch:** `u-lv/fired_heater` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/fired_heater_r1.py` (new; `FiredHeaterR1` plus pure functions);
  - `tests/units/heat/test_fired_heater_r1.py` (new);
  - `data/validation_units/heat/cases/fired_heater.yaml` (new);
  - the `levels.R1` entry of row `fired_heater` in `data/unit_models/heat.yaml`, plus the row `notes`.
  - `units/heat/fired_heater.py` (R0) is NOT edited. Import `fuel_lhv` and `FiredHeater` from it read-only.
- **Read-only imports (verified):**
  - `ngdesign.units.heat.fired_heater.fuel_lhv(fuel_composition: dict[str, float]) -> float` (J per mol of fuel mixture, water as vapour, 298.15 K formation basis)
  - `ngdesign.units.heat.fired_heater.FiredHeater` (identity test)
  - `ngdesign.data.formation.atomic_composition(cid) -> dict[str, int]`
  - `ngdesign.sizing.lmtd.lmtd_counter`
  - `scipy.optimize.brentq`
  - `Thermo.flash_pt`, `flash_ph`
- **Current state:**
  - R0 is `ngdesign.units.heat.fired_heater:FiredHeater`: one process port pair, a `T_out` or `duty_W` spec, a **given** `efficiency` (LHV), optional `fuel_composition`, and `dP`.
  - info: `Q_fired_W`, `fuel_LHV_J_per_mol`, `fuel_molar_flow`.
  - V2083 checks the methane LHV.

## Method

### Equations
1. **Combustion stoichiometry**, per mol of fuel mixture: Σ y_j·atoms_j gives C, H, O, S, N₂.
   - Theoretical O₂ = C + H/4 + S − O/2.
   - Air supplied = (1 + e)·O₂,th / y_O2,air, with e = `excess_air_frac` and the air composition from `air_composition` (default N₂ 0.79 / O₂ 0.21).
   - Flue gas per mol of fuel: CO₂ = C, H₂O = H/2, SO₂ = S, O₂ = e·O₂,th, N₂ = N₂,fuel + air N₂, plus any air argon (complete combustion).
2. **Firebox energy balance**, on the 298.15 K reference, with water as vapour: n_f·LHV + n_air·[h_air(T_air) − h_air(298.15)] = n_fg·[h_fg(T_g) − h_fg(298.15)] + Q_R + Q_loss,R.
   - n_f is the fuel molar flow, n_fg = n_f·ν_fg and n_air = n_f·ν_air.
   - Enthalpies are molar, from `flash_pt` of the air and flue compositions at P_box. Q_loss,R = `radiant_loss_frac`·n_f·LHV.
   - (Wimpress 1963, Hydrocarbon Process. 42(10):115; Kern 1950, Ch. 19 heat balance.)
3. **Lobo–Evans radiant transfer** (Lobo & Evans 1939, Trans. AIChE 35:743; Kern 1950, Ch. 19):
   Q_R = σ·(αA_cp)·𝔉·(T_g⁴ − T_t⁴) + h_c·A_t·(T_g − T_t).
   - The firebox is well stirred, and T_g is the bridgewall (exit) temperature.
   - σ = 5.670374419e-8 W/m²K⁴ (CODATA 2018).
   - αA_cp (m²) and the overall exchange factor 𝔉 are **given params**, read by the user from the Lobo–Evans/Hottel charts. Computing the gas emissivity is out of R1 scope, and the docstring says so.
   - h_c defaults to 11.3565267 W/m²K, the Lobo–Evans assumption of 2 Btu/(h·ft²·°F).
   - T_t = mean process temperature in the radiant coil + `tube_wall_excess_K`.
4. **Convection section** (counter-current flue against process, process enters here first):
   - Q_C = n_fg·[h_fg(T_g) − h_fg(T_stack)];
   - Q_C = UA_C·LMTD(T_g → T_stack against T_proc,in → T_cross), with `UA_convection_W_K` given;
   - process: h_cross = h_in + Q_C/F and h_out = h_cross + Q_R/F.
5. **Process duty** Q = Q_R + Q_C = F·(h_out − h_in), fixed by the R0-style spec (`T_out` or `duty_W`).
   - Efficiency η_LHV = Q/(n_f·LHV).
   - Average radiant flux = Q_R/A_t.

### Algorithm
1. Process outlet exactly as R0: `T_out` → `flash_pt` at P_in − dP; `duty_W` → `flash_ph`. Q = F(h_out − h_in) must be > 0, else refuse as R0 does.
2. LHV = `fuel_lhv(fuel_composition)` (required at R1), plus the stoichiometric ν_air and ν_fg (Eq. 1).
3. **Outer unknown n_f**, by brentq on [Q/LHV·(1 + 1e-9), Q/(η_min·LHV)] with η_min = 0.20. For each n_f:
   - (a) solve T_g from Eqs. 2 = 3 by brentq on [T_t + 1e-6, T_ad], where T_ad is the adiabatic flame temperature (Eq. 2 with Q_R = 0, by brentq on [T_air, 4000 K]). The residual is the Eq. 2 Q_R minus the Eq. 3 Q_R. The process crossover state is needed for T_t, so iterate T_t: start at the mean of the process inlet and outlet; T_t = mean(T_cross, T_out) + excess. Fixed point, |ΔT_t| < 1e-9 K, cap 50.
   - (b) Q_C = Q − Q_R(T_g). If Q_C < 0, the radiant section alone over-delivers, so the fuel is too high: return r = +Q.
   - (c) T_stack from Eq. 4 (flue enthalpy, by brentq on [T_air, T_g]). The process crossover by `flash_ph`.
   - (d) residual r(n_f) = UA_C·LMTD(T_g, T_stack, T_proc,in, T_cross) − Q_C. It **increases** with n_f: more fuel means a hotter, larger flue and less Q_C needed.
     - If LMTD is undefined (T_stack ≤ T_proc,in or T_g ≤ T_cross), the convection section is crossed and the fuel is too low: return r = −Q.
     - The bracket requires r(lo) < 0 < r(hi). If r(hi) ≤ 0, there is no feasible firing rate down to η_min, so raise `FiredHeaterConvergenceError` ("no firing rate").
   - Brent caps: 100 iterations, xtol 1e-12 relative. Each failure raises `FiredHeaterConvergenceError` naming the stage (outer, T_g, T_ad, T_stack, T_t).
4. Outputs: the process outlet (identical to R0). `duty_W` = F(h_out − h_in) (R0 convention), `power_W` = 0.

### Reduction to the lower level
- **Process side:** the R1 process outlet is bit-identical to R0's for the same `T_out`/`duty_W`/`dP`, because it is the same flash call. Test with `==` on T and enthalpy.
- **Fuel:** R0 run with `efficiency` = R1's `info["efficiency_LHV"]` gives `fuel_molar_flow` equal to R1's n_f to 1e-10 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `fuel_composition` missing (required at R1) | `FiredHeaterSpecError(ValueError)` | "fuel_composition" |
| a geometry or heat-transfer param missing or ≤ 0 (`alpha_Acp_m2`, `exchange_factor`, `tube_area_radiant_m2`, `UA_convection_W_K`) | `FiredHeaterSpecError` | the param name |
| `exchange_factor` outside (0, 1]; `excess_air_frac` < 0; `radiant_loss_frac` outside [0, 0.5) | `FiredHeaterSpecError` | the param name |
| a process spec with Q ≤ 0 | ValueError, as R0 | "cannot be satisfied by firing" |
| no feasible n_f in the bracket (η < 20 %) | `FiredHeaterConvergenceError(ValueError)` | "no firing rate" |
| a T_ad or T_g bracket failure | `FiredHeaterConvergenceError` | "T_g" / "adiabatic" |
| the T_t fixed point does not converge | `FiredHeaterConvergenceError` | "tube wall" |

## Params
The R0 params (`T_out` | `duty_W`, `dP`, `fuel_composition`, now required) plus:

| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `excess_air_frac` | number | – | required | ≥ 0 | excess air over stoichiometric |
| `air_composition` | object | mole fraction | {N2: 0.79, O2: 0.21} | sums to 1 | combustion air |
| `air_T_K` | number | K | 298.15 | > 0 | combustion air temperature |
| `box_P_Pa` | number | Pa | 101325 | > 0 | firebox pressure (flue enthalpy) |
| `alpha_Acp_m2` | number | m² | required | > 0 | αA_cp (Lobo–Evans) |
| `exchange_factor` | number | – | required | (0, 1] | overall exchange factor 𝔉 |
| `tube_area_radiant_m2` | number | m² | required | > 0 | A_t (radiant tube outside area) |
| `h_conv_radiant_W_m2K` | number | W/m²K | 11.3565267 | ≥ 0 | radiant-section convection (Lobo–Evans 2 Btu/h·ft²·°F) |
| `tube_wall_excess_K` | number | K | required | ≥ 0 | tube wall above mean radiant process T |
| `UA_convection_W_K` | number | W/K | required | > 0 | convection-section conductance |
| `radiant_loss_frac` | number | – | 0.0 | [0, 0.5) | setting loss as a fraction of fired heat |

```yaml
type: object
required: [fuel_composition, excess_air_frac, alpha_Acp_m2, exchange_factor, tube_area_radiant_m2,
           tube_wall_excess_K, UA_convection_W_K]
properties:
  T_out: {type: number, description: 'outlet temperature spec, K (one of T_out/duty_W)'}
  duty_W: {type: number, description: 'duty spec, W (one of T_out/duty_W)'}
  dP: {type: number, description: 'coil pressure drop, Pa'}
  fuel_composition: {type: object, description: 'fuel component-id map'}
  excess_air_frac: {type: number, description: 'excess air fraction over stoichiometric'}
  air_composition: {type: object, description: 'air mole fractions, default N2 0.79 / O2 0.21'}
  air_T_K: {type: number, description: 'combustion air temperature, K, default 298.15'}
  box_P_Pa: {type: number, description: 'firebox pressure, Pa, default 101325'}
  alpha_Acp_m2: {type: number, description: 'Lobo-Evans alpha*A_cp, m2'}
  exchange_factor: {type: number, description: 'Lobo-Evans overall exchange factor, (0, 1]'}
  tube_area_radiant_m2: {type: number, description: 'radiant tube outside area, m2'}
  h_conv_radiant_W_m2K: {type: number, description: 'radiant-section convection, W/(m2 K), default 11.3565267'}
  tube_wall_excess_K: {type: number, description: 'tube wall above mean radiant process temperature, K'}
  UA_convection_W_K: {type: number, description: 'convection-section UA, W/K'}
  radiant_loss_frac: {type: number, description: 'setting loss fraction of fired heat, default 0'}
```

## Outputs
- **Port:** `outlet`.
- **`duty_W`:** F(h_out − h_in) (R0 convention). **`power_W`:** 0.
- **info:**
  - the R0 keys `Q_fired_W` (= n_f·LHV), `fuel_LHV_J_per_mol`, `fuel_molar_flow`;
  - `efficiency_LHV`, `Q_radiant_W`, `Q_convection_W`, `T_bridgewall_K`, `T_stack_K`, `T_crossover_K`, `T_tube_wall_K`;
  - `T_adiabatic_K`, `radiant_flux_W_m2`, `air_molar_flow`, `flue_molar_flow`, `flue_y_O2`.

## Tests
- **Closed-form** (pure functions, independent numbers from `calc_fired_heater.py`):
  1. **Stoichiometry:** methane, 15 % excess, air 0.79/0.21.
     - O₂,th = 2; air = 10.952381 mol/mol fuel; flue = 11.952381 mol/mol fuel.
     - Flue y: CO₂ 0.083665339, H₂O 0.167330677, O₂ 0.025099602, N₂ 0.723904382 (rel 1e-8).
  2. **Lobo–Evans:** αA_cp 60 m², 𝔉 0.6, T_g 1100 K, T_t 650 K, h_c 11.36, A_t 200 m².
     - Q_rad = 2624327.25 W, Q_conv = 1022400 W, Q_R = 3646727.25 W, flux 18233.6362 W/m² (rel 1e-9).
  3. **Unit conversion:** 2 Btu/(h·ft²·°F) = 11.3565267 W/(m²K), used as the h_c default.
- **Identity:** both reductions above, on `example_case`.
  - The R0 example: methane fuel heating natural gas 300 → 600 K, 100 mol/s, 5 bar.
  - Add a geometry sized for it: Q ≈ 1.3 MW, so choose A_t, αA_cp, 𝔉 and UA_C giving an efficiency of 80–90 %. Record the measured η in the test docstring.
- **Energy self-consistency:** fuel LHV·n_f + air sensible = Q + flue sensible at T_stack + losses, to 1e-8 relative. This is an independent re-evaluation in the test from the reported info and `flash_pt`.
- **Refusals:** one per table row. The "no firing rate" case uses UA_C so small, with 𝔉 tiny, that η < 20 %.
- **V1 candidates:**
  - Kern (1950), Ch. 19, furnace example worked by the Wilson–Lobo–Hottel / Lobo–Evans method. It prints the inputs (fuel, excess air, αA_cp, 𝔉, A_t) and the results (radiant duty, bridgewall temperature).
  - Wimpress (1963), Hydrocarbon Processing 42(10), worked example.
  - Transcribe printed numbers only. Kern uses an HHV basis and chart enthalpies, so expect assessed misses.
  - If neither is accessible: "V1 gap: searched Kern 1950 Ch. 19, Wimpress 1963, API 560 annexes".

## Steps
1. Pure functions: stoichiometry and flue composition, Lobo–Evans Q_R, h_c conversion, with closed-form tests 1–3 and the param refusals. Push.
2. The T_ad and T_g solves and the T_t fixed point, with flue enthalpies via `flash_pt` (pure functions taking `thermo`). Then the outer n_f brentq, convection-section T_stack and crossover. Push.
3. The adapter `FiredHeaterR1`, info, `example_case`; the identity and energy self-consistency tests, the remaining refusals. Push.
4. The YAML `levels.R1`, the V1 case or gap, harness runs. Push and request review.

## Review checklist
- The stoichiometry uses `atomic_composition`. Excess O₂ appears in the flue. Fuel N₂ is passed through.
- The firebox energy balance uses one consistent reference (298.15 K, water vapour), matching `fuel_lhv`.
- σ is the CODATA value. αA_cp and 𝔉 are params, with no hidden chart digitising.
- Each brentq and the fixed point have caps and stage-named typed errors.
- The process outlet is computed exactly as R0 does. R0's efficiency path is untouched.
