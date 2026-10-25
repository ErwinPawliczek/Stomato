# shell_tube R1, R2: Kern-method rating against a utility stream; zoned phase change and temperature-cross check

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, then R2 built on R1; both from catalogue `planned` to `provisional`.
- **Depends on:**
  - the U-R2 conventions and U-01d (#243);
  - **T-PP** (`Thermo.phase_props` transport properties; see the double_pipe spec);
  - **double_pipe R1 merged**, because this unit imports `ngdesign.units.heat.rating` read-only.
- **Wave/order:** after double_pipe; parallel with plate_exchanger and air_cooler.
- **Branch:** `u-lv/shell_tube` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/shell_tube_r1.py` (new; `ShellTubeR1` plus the Kern pure functions);
  - `src/ngdesign/units/heat/shell_tube_r2.py` (new; `ShellTubeR2` plus the zoning and phase-change pure functions);
  - `tests/units/heat/test_shell_tube_r1.py`, `tests/units/heat/test_shell_tube_r2.py` (new);
  - `data/validation_units/heat/cases/shell_tube.yaml` (new);
  - the `levels.R1` and `levels.R2` entries of row `shell_tube` in `data/unit_models/heat.yaml`, plus the row `notes` line.
  - **`units/heat_exchange.py` is NOT edited.** It holds the shared R0 class for heater, cooler, air_cooler and shell_tube.
- **Read-only imports (verified, `ht` 1.2.0 / `fluids` 1.3.1):**
  - `ngdesign.units.heat.rating`: `film_props`, `inlet_kind`, `duct_h`, `darcy_dP`, `u_outside_tube`, `rate_two_stream`, `RatingError`, `SinglePhaseRequired`, `PropertyUnavailable`, `RatingConvergenceError` (double_pipe spec API);
  - `ht.effectiveness_from_NTU(NTU, Cr, subtype='S&T', n_shell_tube=n)`. Checked equal to the Incropera 11.31a/b closed form: 0.539939556 for one shell and 0.558304442 for two, at NTU 1, C_r 0.5;
  - `ht.F_LMTD_Fakheri(Thi, Tho, Tci, Tco, shells=1) -> float`. Checked equal to the Bowman analytic 1-2 F: 0.926902303 at (450, 370, 300, 340);
  - `ht.Shah(m, x, D, rhol, mul, kl, Cpl, P, Pc) -> float` (in-tube condensation, Shah 1979);
  - `ht.Liu_Winterton(m, x, D, rhol, rhog, mul, kl, Cpl, MW, P, Pc, Te) -> float` (in-tube flow boiling, Liu & Winterton 1991);
  - `ngdesign.sizing.lmtd.lmtd_counter`;
  - `ngdesign.units._physics.heat_balance.TemperatureCross`;
  - `Thermo.flash_ph`, `flash_pt`, `phase_props`, `bubble_point`, `dew_point`.
  - **Not used:** `ht.dP_Kern`. It interpolates a scanned chart and supports square pitch only, so the Kern ΔP is implemented explicitly from Eq. S3 below.
- **Current state:**
  - R0 is `ngdesign.units.heat_exchange:HeatExchanger`: ports `inlet` → `outlet`, a `T_out` or `duty_W` spec with `dP`, `duty_W` = F·Δh, info `duty_kW`.
  - **The row has ONE process port pair.** The catalogue fixes ports per row (U-01c), so R1 and R2 keep `inlet` → `outlet`. The other side is a **utility stream described by params**: composition, T, P and flow. It is computed internally, is not a port, and is reported in info.

## Method

### Equations (R1)
- **Tube side**, with N_t tubes, N_tp passes, D_i/D_o and length L per pass:
  - A_flow = (N_t/N_tp)·πD_i²/4 and D_h = D_i;
  - h_i, Re and f_D from `rating.duct_h` (Gnielinski or laminar 3.66; double_pipe Eqs. 2–4);
  - ΔP_t = N_tp·f_D(L/D_i)ρv²/2 + 4N_tp·ρv²/2. The second term is Kern's return loss (Kern 1950, Ch. 7, tube-side pressure drop; Kakaç, Liu & Pramuanjaroenkij, *Heat Exchangers*, 3rd ed., §8 "Kern method").
- **Shell side** (Kern 1950, Ch. 7; Kakaç et al. 3rd ed., Ch. 8):
  - S1: a_s = D_s·C′·B/P_T, with C′ = P_T − D_o and B the baffle spacing; G_s = ṁ/a_s.
  - S2: the equivalent diameter.
    - Triangular 30°: D_e = 4(√3/4·P_T² − πD_o²/8)/(πD_o/2).
    - Square 90°: D_e = 4(P_T² − πD_o²/4)/(πD_o).
    - Re_s = D_e·G_s/μ, and h_o = 0.36(k/D_e)Re_s^0.55·Pr^⅓·(μ/μ_w)^0.14, with (μ/μ_w) = 1 at R1, stated in the docstring.
    - Validity: 2·10³ < Re_s < 10⁶ (Kern).
  - S3: f = exp(0.576 − 0.19·ln Re_s), valid for 400 < Re_s ≤ 10⁶, the Kakaç et al. analytic fit to Kern's shell friction chart. ΔP_s = f·G_s²·(N_b + 1)·D_s/(2ρD_e), with φ_s = 1.
- **Wall and U** (outside-tube area A_o = N_t·πD_o·L): `rating.u_outside_tube(h_i, h_o, D_o, D_i, k_w, R_fi, R_fo)`, with h_i/h_o assigned by `process_side`.
- **Thermal model:** TEMA E shell, N_tp ∈ {1, 2, 4, 6, 8}, and `n_shells` in series.
  - ε = `ht.effectiveness_from_NTU(NTU, Cr, 'S&T', n_shell_tube=n_shells)` for N_tp ≥ 2. This is Incropera eqs. 11.31a/b, with each shell taking NTU/n.
  - ε = `'counterflow'` for N_tp = 1 with n_shells = 1.
  - N_tp = 1 with n_shells > 1 is refused, because a pure counterflow series is just a longer counterflow unit.
- **Reported F:** `ht.F_LMTD_Fakheri(Thi, Tho, Tci, Tco, shells=n_shells)` at the converged terminal temperatures, as info only.

### Algorithm (R1)
1. Validate. Build the utility inlet state: `flash_pt(utility_composition, utility_T_K, utility_P_Pa, utility_molar_flow)`.
2. Hot and cold assignment: whichever of the process and utility inlets is hotter is "hot". If they are equal (within 1e-9 K), refuse with `TemperatureCross`.
3. Single-phase check on both inlets (`rating.inlet_kind`); a phase change goes to R2 (`SinglePhaseRequired`, with the message "use model R2").
4. ΔP for the tube and shell sides from inlet properties (Eqs. S3 and the tube equation), then the outlet pressures.
5. `rating.rate_two_stream(hot, cold, thermo, P_h_out, P_c_out, ua_of, eps_of)`. Here `ua_of` evaluates both films at the side means (`film_props`) and returns U_o·A_o; `eps_of` is ε as above.
6. Before accepting the result, check the shell-side Re_s at mean properties against [2000, 10⁶]. Outside it, raise `KernRangeError`, naming Re_s, unless `allow_extrapolation: true`; in that case set `info["kern_in_range"] = 0.0`.
7. **Outputs:**
   - the process outlet is the rated outlet of the process side;
   - `UnitResult.duty_W` = F_proc·(h_out − h_in), the heat into the process (the R0 sign convention), so V0 closes on the single port pair;
   - the utility outlet T, P and duty go in info.

### Equations and algorithm (R2)
- **Zone analysis** (Serth & Lestina, *Process Heat Transfer*, 2nd ed., Ch. 11, zone analysis; Kern 1950, Ch. 12–13), counter-current pairing.
  1. For a trial duty Q, split the **process** enthalpy span into `n_zones` equal-ΔH zones (default 20). The process states at the zone boundaries come from `flash_ph`.
  2. The utility states at the matching boundaries come from the utility energy balance, also by `flash_ph`, so a condensing or boiling utility is zoned too.
- **Per zone k:**
  - local h for each side at the zone-mean state;
  - U_k from `u_outside_tube`;
  - ΔT_lm,k from `lmtd_counter` on the four boundary temperatures;
  - ΔA_k = ΔQ_k/(U_k·ΔT_lm,k).
  - If a zone's ΔT ≤ 0, that is an internal cross: raise `TemperatureCross` with the zone temperatures.
- **Local h by phase regime** (the zone-mean vapour fraction x_v from the flash):
  - **single phase:** the R1 correlations (Gnielinski tube, Kern shell);
  - **shell-side condensation** (vapour condensing on horizontal tubes): Nusselt film,
    - h_1 = 0.729[g·ρ_l(ρ_l − ρ_v)·k_l³·h′_fg/(μ_l(T_sat − T_w)D_o)]^¼ (Incropera eq. 10.46), with h′_fg = h_fg + 0.68·c_p,l(T_sat − T_w) (Incropera eq. 10.9);
    - bank: h = h_1·N_r^(−¼) (Incropera eq. 10.47), where N_r is the mean number of tubes in a vertical row, given as the param `tube_rows_vertical`.
    - T_w comes from a wall-temperature fixed point: T_w = T_sat − U_k(T_sat − T_util)/h_cond, starting at T_w = (T_sat + T_util)/2, |ΔT_w| < 1e-6 K, cap 50, else `RatingConvergenceError`.
    - h_fg is the zone's latent heat: the enthalpy difference between the dew and bubble states at the zone pressure, from `dew_point`/`bubble_point` plus `flash_pt`.
  - **tube-side condensation:** `ht.Shah`, with x = the zone-mean quality, D = D_i and ṁ per tube.
  - **tube-side flow boiling:** `ht.Liu_Winterton`, with T_e = T_w − T_sat from the same fixed point.
  - **shell-side boiling:** refused (`PhaseRegimeNotRated`: "shell-side boiling (kettle/thermosiphon) is not rated at R2").
- **Rating solve:** brentq on Q ∈ (1e-6·Q_max, Q_max) with g(Q) = Σ_k ΔA_k(Q)/F_corr − A_o. Here F_corr = 1 for N_tp = 1, and otherwise `F_LMTD_Fakheri` at the terminal temperatures, applied uniformly. That uniform F is a stated approximation (Serth Ch. 11). xtol 1e-10·Q_max, maxiter 100.
- **Multi-pass temperature cross:** after convergence with N_tp ≥ 2,
  - if F is not finite, or F < `F_min` (default 0.75, Kern's practical limit, Ch. 7), raise `TemperatureCross`;
  - name F, and the minimum shells in series n* = the smallest n ≤ 10 with `F_LMTD_Fakheri(..., shells=n)` ≥ `F_min`;
  - also report `info["shells_required"]`.

### Reduction to the lower level
- **R1 → R0:** R0 (`HeatExchanger`) with `duty_W` = R1's process duty and `dP` = R1's process ΔP gives the R1 process outlet to 1e-10 relative (same `flash_ph`).
- **R2 → R1:** with a single-phase process and utility, `n_zones=1` and N_tp = 1, R2's converged Q equals R1's Q to 1e-8 relative. For constant-C counterflow, Q = UA·LMTD is algebraically ε-NTU, and the one-zone U uses the same mean-state films.
  - With N_tp = 2 and one shell, the same test holds against R1 with ε from TEMA E, because Fakheri's F is exact for 1-2N. The independent check `calc_shell_tube.py` gives Q_ε = 2106190.92984 = UA·F·LMTD.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| a geometry value missing or ≤ 0; `pitch_m ≤ tube_OD_m`; `tube_OD_m ≤ tube_ID_m` | `ShellTubeGeometryError(ValueError)` (in `shell_tube_r1.py`) | the param name |
| `tube_passes` ∉ {1, 2, 4, 6, 8}; `layout` ∉ {"triangular30", "square90"}; `process_side` ∉ {"tube", "shell"} | `ShellTubeGeometryError` | the param name |
| `tube_passes == 1` and `n_shells > 1` | `ShellTubeGeometryError` | "n_shells" |
| utility params missing; utility flow ≤ 0 | `ShellTubeGeometryError` | "utility_" + the field name |
| the process and utility inlets at the same T | `TemperatureCross` | "inlet temperatures" |
| a phase change at R1 | `SinglePhaseRequired` | "use model R2" |
| Re_s outside [2000, 1e6] without `allow_extrapolation` | `KernRangeError(RatingError)` | "Re_s" |
| shell-side boiling at R2 | `PhaseRegimeNotRated(RatingError)` (in `shell_tube_r2.py`) | "shell-side boiling" |
| F not finite or < F_min at R2 | `TemperatureCross` | "F", "shells_required" |
| a zone with ΔT ≤ 0 | `TemperatureCross` | "zone" |
| no convergence | `RatingConvergenceError` | "did not converge" |

## Params (R1; R2 adds the last three)
| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `process_side` | string | – | required | tube/shell | where the process stream flows |
| `shell_ID_m` | number | m | required | > 0 | shell inside diameter D_s |
| `n_tubes` | integer | – | required | ≥ 1 | total tubes N_t |
| `tube_OD_m`, `tube_ID_m` | number | m | required | OD > ID > 0 | tube diameters |
| `tube_length_m` | number | m | required | > 0 | tube length per pass L |
| `pitch_m` | number | m | required | > tube_OD_m | tube pitch P_T |
| `layout` | string | – | required | triangular30/square90 | tube layout |
| `baffle_spacing_m` | number | m | required | > 0 | B |
| `n_baffles` | integer | – | required | ≥ 1 | N_b |
| `tube_passes` | integer | – | required | 1, 2, 4, 6, 8 | N_tp |
| `n_shells` | integer | – | 1 | ≥ 1 | TEMA E shells in series |
| `utility_composition` | object | mole fraction | required | sums to 1 | utility stream |
| `utility_T_K`, `utility_P_Pa`, `utility_molar_flow` | number | K, Pa, mol/s | required | > 0 | utility inlet state |
| `k_wall_W_mK` | number | W/m/K | 45.0 | > 0 | tube wall |
| `R_f_tube_m2K_W`, `R_f_shell_m2K_W` | number | m²K/W | 0.0 | ≥ 0 | fouling |
| `roughness_m` | number | m | 4.5e-5 | ≥ 0 | tube roughness |
| `allow_extrapolation` | boolean | – | false | – | allow Kern outside 2e3–1e6 (flagged in info) |
| `n_zones` (R2) | integer | – | 20 | 1–200 | zones |
| `tube_rows_vertical` (R2) | integer | – | required if shell-side condensation | ≥ 1 | N_r for Eq. 10.47 |
| `F_min` (R2) | number | – | 0.75 | (0, 1) | minimum acceptable F |

```yaml
# R1 (R2: the same plus n_zones, tube_rows_vertical, F_min)
type: object
required: [process_side, shell_ID_m, n_tubes, tube_OD_m, tube_ID_m, tube_length_m, pitch_m, layout,
           baffle_spacing_m, n_baffles, tube_passes, utility_composition, utility_T_K, utility_P_Pa,
           utility_molar_flow]
properties:
  process_side: {type: string, enum: [tube, shell], description: 'side the process stream flows on'}
  shell_ID_m: {type: number, description: 'shell inside diameter, m'}
  n_tubes: {type: integer, description: 'total tube count'}
  tube_OD_m: {type: number, description: 'tube outside diameter, m'}
  tube_ID_m: {type: number, description: 'tube inside diameter, m'}
  tube_length_m: {type: number, description: 'tube length per pass, m'}
  pitch_m: {type: number, description: 'tube pitch, m'}
  layout: {type: string, enum: [triangular30, square90], description: 'tube layout'}
  baffle_spacing_m: {type: number, description: 'baffle spacing, m'}
  n_baffles: {type: integer, description: 'baffle count'}
  tube_passes: {type: integer, enum: [1, 2, 4, 6, 8], description: 'tube passes per shell'}
  n_shells: {type: integer, description: 'TEMA E shells in series, default 1'}
  utility_composition: {type: object, description: 'utility mole fractions'}
  utility_T_K: {type: number, description: 'utility inlet temperature, K'}
  utility_P_Pa: {type: number, description: 'utility inlet pressure, Pa'}
  utility_molar_flow: {type: number, description: 'utility flow, mol/s'}
  k_wall_W_mK: {type: number, description: 'tube wall conductivity, W/(m K), default 45'}
  R_f_tube_m2K_W: {type: number, description: 'tube-side fouling, m2 K/W, default 0'}
  R_f_shell_m2K_W: {type: number, description: 'shell-side fouling, m2 K/W, default 0'}
  roughness_m: {type: number, description: 'tube roughness, m, default 4.5e-5'}
  allow_extrapolation: {type: boolean, description: 'permit Kern outside 2e3 < Re_s < 1e6'}
```

## Outputs
- **Port:** `outlet` (the process).
- **`duty_W`:** heat into the process, F·(h_out − h_in), the R0 convention. **`power_W`:** 0.
- **info (R1):**
  - `Q_W` (heat transferred, positive), `U_W_m2K`, `A_m2`, `UA_W_K`, `NTU`, `effectiveness`, `F_LMTD`, `LMTD_K`;
  - `h_tube_W_m2K`, `h_shell_W_m2K`, `Re_tube`, `Re_shell`, `dP_tube_Pa`, `dP_shell_Pa`;
  - `utility_T_out_K`, `utility_P_out_Pa`, `utility_duty_W`, `kern_in_range`.
- **info (R2) adds:** `n_zones`, `A_required_m2`, `shells_required`, `min_zone_dT_K`, `zone_U_min_W_m2K`, `zone_U_max_W_m2K`.

## Tests
- **Closed-form R1** (pure functions, independent numbers from `calc_shell_tube.py`, rel 1e-8). Geometry G1:
  - D_s 0.489 m; 158 tubes, 19.05/14.83 mm; L 4.877 m; P_T 23.81 mm triangular; B 0.3048 m; 15 baffles; 2 passes.
  1. **Shell (Kern):** ṁ 18 kg/s, ρ 995, μ 8.0e-4, k 0.615, cp 4180.
     - Expect a_s = 0.0297969203 m², D_e,tri = 0.0137644071, D_e,sq = 0.0188408135, G_s = 604.089276, Re_s = 10393.6634, Pr = 5.43739837.
     - Expect h_o = 4579.02747 W/m²K, f = 0.306879289, ΔP_s = 31988.0737 Pa.
  2. **Tube:** ṁ 12 kg/s, ρ 700, μ 4.0e-4, k 0.12, cp 2300, ε 4.5e-5.
     - Expect A/pass = 0.0136458086, v = 1.25627273, Re = 32603.4179, f_D = 0.0297781346, Nu = 278.547286, h_i = 2253.92274, ΔP_t = 15237.7172 Pa.
  3. **U and area:** clean U_o (k_w 45) = 1188.61873; A_o = 46.1163254 m²; UA = 54814.7284 W/K.
  4. **Effectiveness:** ε for 1-2, NTU 1, C_r 0.5 = 0.539939556 (two shells: 0.558304442); NTU 2, C_r 0.8 = 0.60699508 (two shells: 0.6798335).
  5. **F:** F_1-2(450, 370, 300, 340) = 0.926902303 (R = 2, P = 0.266666667).
- **Closed-form R2:** Nusselt condensation with ρ_l 600, ρ_v 20, k_l 0.10, μ_l 2.0e-4, c_p,l 2500, h_fg 3.0e5 J/kg, T_sat 330 K, T_w 320 K, D_o 0.01905 m:
  - h′_fg = 317000;
  - single tube h_1 = 1682.81386 W/m²K;
  - bank, N_r = 10: 946.315775.
- **Identity:** R1 → R0 and R2 → R1 as above. Use a constant-cp fake `Thermo` for the exact 1e-8 version, and the real `pr` package on the example case for the 1e-10 outlet identity.
- **Refusals:** one test per table row. The cross test uses a 1-2 exchanger with a steep temperature cross (process 450 → required to approach a utility at 440, high UA), which converges and then fails F_min.
- **V1 candidates:**
  - Kern (1950), Example 7.3 or 7.4 (shell-and-tube, Kern method). These print the inputs (rates, temperatures, TEMA geometry) and the computed h_io, h_o, U_C, U_D and ΔP_s/ΔP_t.
  - Kakaç, Liu & Pramuanjaroenkij, 3rd ed., Ch. 8 worked example(s) on the Kern method, with the same kind of printed values.
  - Transcribe only printed numbers. Kern's chart-read j_H gives misses of a few %, which are `assessed`.
  - R2: Kern (1950), Ch. 12 condenser example (printed condensing coefficients). If it is not accessible, record a gap: "searched Kern Ch. 12, Serth 2nd ed. Ch. 11 examples".

## Steps
1. `shell_tube_r1.py` pure functions: S1–S3 shell side, the tube-side ΔP with returns, the geometry validation and errors, with closed-form tests 1–3. Push.
2. `ShellTubeR1` adapter: the utility state, hot/cold assignment, ε via `'S&T'`, the rating via `rating.rate_two_stream`, info, the range flag, and `example_case`. The example is the R0 slice gas cooled by cooling water (H₂O, 303.15 K, 4 bar) on the shell side with geometry G1 (adjust n_tubes or flow so Kern Re is in range). Closed-form tests 4–5, the R1→R0 identity, refusals. Push.
3. The YAML `levels.R1`, the V1 case or gap, harness write-doc and `--audit`. Push. **This is the R1 review point.**
4. `shell_tube_r2.py` pure functions: Nusselt bank condensation with h′_fg, the wall-temperature fixed point, regime selection (Shah, Liu-Winterton calls), and zone construction from PH flashes, with the R2 closed-form test. Push.
5. `ShellTubeR2` adapter: the zone-sum rating solve, the F_min/shells_required check, the R2→R1 identity (fake Thermo), the refusals and the condensing example (the process is a C3/C4 vapour condensed by cooling water). Push.
6. The YAML `levels.R2` (`end_state: true` stays on R2), the V1 case or gap, harness runs. Push and request review.

## Review checklist
- The shell-side constants are 0.36, 0.55, ⅓ and exp(0.576 − 0.19 ln Re). D_e is per layout. a_s uses C′ = P_T − D_o.
- Tube ΔP includes 4·N_tp velocity heads. Velocity uses tubes per pass.
- The ε subtype is `'S&T'` with `n_shell_tube` for N_tp ≥ 2. N_tp = 1 with several shells is refused.
- The utility is never a port, and process `duty_W` follows the R0 sign. V0 closes.
- R2 zones are equal-ΔH in the process. Utility boundaries come from its own `flash_ph`. Zone LMTD uses `lmtd_counter`. The F application and the F_min refusal are present.
- Every fixed point and brentq has a cap and a typed error. Phase regimes are chosen from the flash vapour fraction, not guessed.
- `heat_exchange.py` and `rating.py` are untouched.
