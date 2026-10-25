# air_cooler R1: finned-tube bundle rating (Briggs-Young air side, ESDU air ΔP, fan power)

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional` (`end_state: true` stays on R1).
- **Depends on:**
  - the U-R2 conventions, U-01d (#243) and **T-PP** (`phase_props` transport properties; see the double_pipe spec);
  - **double_pipe R1 merged** (it imports `ngdesign.units.heat.rating`).
- **Wave/order:** after double_pipe; parallel with shell_tube and plate_exchanger.
- **Branch:** `u-lv/air_cooler` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/air_cooler_r1.py` (new; `AirCoolerR1` plus pure functions);
  - `tests/units/heat/test_air_cooler_r1.py` (new);
  - `data/validation_units/heat/cases/air_cooler.yaml` (new);
  - the `levels.R1` entry of row `air_cooler` in `data/unit_models/heat.yaml`, plus the row `notes`.
  - **`units/heat_exchange.py` is NOT edited.**
- **Read-only imports (verified, `ht` 1.2.0 / `fluids` 1.3.1):**
  - `fluids.geometry.AirCooledExchanger(tube_rows, tube_passes, tubes_per_row, tube_length, tube_diameter, fin_thickness, angle=None, pitch=None, pitch_parallel=None, pitch_normal=None, pitch_ratio=None, fin_diameter=None, fin_height=None, fin_density=None, fin_interval=None, parallel_bays=1, bundles_per_bay=1, fans_per_bay=1, corbels=False, tube_thickness=None, fan_diameter=None)`. It exposes `A`, `A_min`, `A_increase`, `A_fin`, `A_tube_showing`, `A_bare_tube`, `Di`, `A_tube_flow`, `tubes`, `fin_diameter`, `bare_length`, `pitch_parallel`, `pitch_normal`, `flow_area_contraction_ratio` and `tube_rows`.
  - `ht.h_Briggs_Young(m, A, A_min, A_increase, A_fin, A_tube_showing, tube_diameter, fin_diameter, fin_thickness, bare_length, rho, Cp, mu, k, k_fin) -> float`. **It returns h on the BARE-TUBE outside-area basis**, already including the Kern–Kraus fin efficiency and multiplied by `A_increase` (verified in source).
  - `ht.fin_efficiency_Kern_Kraus(Do, D_fin, t_fin, k_fin, h) -> float` (info only)
  - `ht.dP_ESDU_high_fin(m, A_min, A_increase, flow_area_contraction_ratio, tube_diameter, pitch_parallel, pitch_normal, tube_rows, rho, mu) -> float`
  - `ht.Ft_aircooler(Thi, Tho, Tci, Tco, Ntp=1, rows=1) -> float`. Its source **silently falls back to "a bad assumption"** coefficients for unsupported (Ntp, rows) pairs, so this unit refuses those pairs itself (see the refusals).
  - `ngdesign.units.heat.rating`: `film_props`, `inlet_kind`, `duct_h`, `darcy_dP`, the errors
  - `ngdesign.sizing.lmtd.lmtd_counter`, `scipy.optimize.brentq`
- **Current state:**
  - R0 is the shared `HeatExchanger`: `inlet` → `outlet`, a T_out or duty spec with dP.
  - R1 keeps that single process port pair. The **air side is ambient, described by params**, and is internal: not a port, reported in info.

## Method

### Equations
1. **Geometry:** `AirCooledExchanger(...)` from the params, with all lengths in m.
2. **Air side** (Briggs & Young 1963, Chem. Eng. Prog. Symp. Ser. 59(41); ESDU 86022):
   - V_max = ṁ_air/(A_min·ρ), Re = ρV_max·D_o/μ;
   - Nu = 0.134·Re^0.681·Pr^⅓·(s/l_f)^0.2·(s/t_f)^0.1134, where s = `bare_length` (the fin gap) and l_f = (D_fin − D_o)/2;
   - h_fin = Nu·k/D_o;
   - η_f from Kern–Kraus annular fins (Kern & Kraus, *Extended Surface Heat Transfer*, 1972; Bessel form);
   - h_bare = (η_f·A_fin + A_tube_showing)/A·h_fin·A_increase. This is exactly `ht.h_Briggs_Young`.
   - Validity (Briggs–Young): 1000 < Re < 8000.
3. **Air ΔP** (ESDU 86022, high fin):
   - K_f = 4.567·Re^−0.242·A_increase^0.504·(p_n/D_o)^−0.376·(p_p/D_o)^−0.546;
   - K_a = 1 + σ², with σ = `flow_area_contraction_ratio`;
   - ΔP_air = (K_a + N_rows·K_f)·ρV_max²/2.
4. **Fan power:** W_fan = (ṁ_air/ρ_in)·ΔP_air/η_fan. It is reported in info only: it goes into the air, not the process, so it is not `power_W`.
5. **Tube side:** `rating.duct_h` with A_flow = `A_tube_flow`·(tubes/tube_passes), where A_tube_flow is per tube, and D_h = `Di`. ΔP_t = N_tp·f_D(L/D_i)ρv²/2 + 4N_tp·ρv²/2, the header/return losses as in Kern Ch. 7.
6. **Overall**, bare outside area A_b = `A_bare_tube`:
   1/U_b = 1/h_bare + D_o·ln(D_o/D_i)/(2k_w) + R_fi·D_o/D_i + D_o/(D_i·h_i).
7. **Thermal:** Q = U_b·A_b·F_t·LMTD_cf. F_t = `ht.Ft_aircooler(Thi, Tho, Tci, Tco, Ntp, rows)` (VDI Heat Atlas; Roetzel–Spang crossflow fits). LMTD_cf = `lmtd_counter` on the terminal temperatures.

### Algorithm
1. Validate the params, and build the geometry object.
   - Refuse unsupported (tube_passes, tube_rows) pairs. Supported: (1, 1–4), (2, 2), (2, 4), (3, 3) and (4, 4), the explicit branches in `Ft_aircooler`. Passes = rows > 4 is also allowed, as ht's documented "reasonable assumption"; flag it in info.
2. The process inlet must be single phase (`rating.inlet_kind`). Condensing service is not rated at R1 (`SinglePhaseRequired`).
3. **Air inlet state:** `flash_pt(air_composition, air_T_K, air_P_Pa, n_air)`, with n_air = ṁ_air/MW_air from `phase_props`. Default composition {N2: 0.79, O2: 0.21}, dry air.
4. ΔP_tube from process inlet properties; ΔP_air from air inlet properties.
5. Unknown Q, by brentq on (1e-6·Q_max, Q_max).
   - Q_max = min(process enthalpy drop to air_T_K, air enthalpy rise to the process inlet T), from `flash_pt`.
   - g(Q) = U_b(films at the side means)·A_b·F_t(terminal T(Q))·LMTD(T(Q)) − Q.
   - g > 0 at Q_lo (LMTD > 0) and g < 0 as Q → Q_max (LMTD → 0). Evaluate g at Q_hi = Q_max·(1 − 1e-9) so that LMTD stays defined.
   - If `Ft_aircooler` returns a non-finite value or ≤ 0 at some Q, set g = −Q there; that point is infeasible in crossflow.
   - xtol 1e-12·Q_max, maxiter 100. On failure, `RatingConvergenceError`.
6. Check Re_air at the converged mean air state against (1000, 8000). Outside it, raise `BriggsYoungRangeError`, unless `allow_extrapolation`; then flag `info["briggs_young_in_range"] = 0.0`.
7. **Outputs:** the process outlet by `flash_ph` at the converged Q; `duty_W` = F_proc·(h_out − h_in), negative for cooling (the R0 convention); `power_W` = 0.

### Reduction to the lower level
R0 `HeatExchanger` with `duty_W` = R1's `duty_W` and `dP` = R1's tube ΔP reproduces R1's process outlet to 1e-10 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| a geometry value missing or ≤ 0; unsupported fin spec (exactly one of fin_density/fin_interval and one of fin_height/fin_diameter is required) | `AirCoolerGeometryError(ValueError)` | the param name |
| (tube_passes, tube_rows) not supported | `AirCoolerGeometryError` | "tube_passes/tube_rows" |
| air flow ≤ 0, fan efficiency outside (0, 1] | `AirCoolerGeometryError` | "air_mass_flow_kg_s" / "fan_efficiency" |
| the process inlet at or below the air inlet temperature | `TemperatureCross` | "air inlet" |
| a two-phase process inlet, or a phase change during the duty | `SinglePhaseRequired` | "R1 rates single-phase duty" |
| missing transport properties | `PropertyUnavailable` | the property |
| Re_air outside (1000, 8000) without `allow_extrapolation` | `BriggsYoungRangeError(RatingError)` | "Re_air" |
| no convergence | `RatingConvergenceError` | "did not converge" |

## Params
| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `tube_rows`, `tube_passes`, `tubes_per_row` | integer | – | required | ≥ 1 | bundle layout |
| `tube_length_m` | number | m | required | > 0 | tube length |
| `tube_OD_m`, `tube_wall_m` | number | m | required | > 0 | bare tube OD and wall thickness |
| `fin_thickness_m` | number | m | required | > 0 | fin thickness |
| `fin_height_m` or `fin_diameter_m` | number | m | exactly one | > 0 | fin geometry |
| `fin_density_per_m` or `fin_interval_m` | number | 1/m or m | exactly one | > 0 | fin spacing |
| `pitch_m` + `angle_deg`, or `pitch_parallel_m` + `pitch_normal_m` | number | m, deg | one pair | > 0 | tube pitch |
| `parallel_bays`, `bundles_per_bay` | integer | – | 1 | ≥ 1 | multiples |
| `k_fin_W_mK` | number | W/m/K | 205.0 | > 0 | fin conductivity (aluminium) |
| `k_wall_W_mK` | number | W/m/K | 45.0 | > 0 | tube wall |
| `R_f_tube_m2K_W` | number | m²K/W | 0.0 | ≥ 0 | tube-side fouling |
| `roughness_m` | number | m | 4.5e-5 | ≥ 0 | tube roughness |
| `air_T_K`, `air_P_Pa` | number | K, Pa | required, 101325 | > 0 | ambient air |
| `air_mass_flow_kg_s` | number | kg/s | required | > 0 | total air flow |
| `air_composition` | object | mole fraction | {N2: 0.79, O2: 0.21} | sums to 1 | air |
| `fan_efficiency` | number | – | required | (0, 1] | total fan efficiency |
| `allow_extrapolation` | boolean | – | false | – | permit Briggs–Young outside its Re range |

```yaml
type: object
required: [tube_rows, tube_passes, tubes_per_row, tube_length_m, tube_OD_m, tube_wall_m, fin_thickness_m,
           air_T_K, air_mass_flow_kg_s, fan_efficiency]
properties:
  tube_rows: {type: integer, description: 'tube rows in the air flow direction'}
  tube_passes: {type: integer, description: 'tube-side passes'}
  tubes_per_row: {type: integer, description: 'tubes per row'}
  tube_length_m: {type: number, description: 'tube length, m'}
  tube_OD_m: {type: number, description: 'bare tube outside diameter, m'}
  tube_wall_m: {type: number, description: 'tube wall thickness, m'}
  fin_thickness_m: {type: number, description: 'fin thickness, m'}
  fin_height_m: {type: number, description: 'fin height, m (or fin_diameter_m)'}
  fin_diameter_m: {type: number, description: 'fin outside diameter, m (or fin_height_m)'}
  fin_density_per_m: {type: number, description: 'fins per metre (or fin_interval_m)'}
  fin_interval_m: {type: number, description: 'fin pitch, m (or fin_density_per_m)'}
  pitch_m: {type: number, description: 'tube pitch, m (with angle_deg)'}
  angle_deg: {type: number, description: 'layout angle, deg (30 triangular)'}
  pitch_parallel_m: {type: number, description: 'pitch parallel to air flow, m'}
  pitch_normal_m: {type: number, description: 'pitch normal to air flow, m'}
  parallel_bays: {type: integer, description: 'bays, default 1'}
  bundles_per_bay: {type: integer, description: 'bundles per bay, default 1'}
  k_fin_W_mK: {type: number, description: 'fin conductivity, W/(m K), default 205'}
  k_wall_W_mK: {type: number, description: 'tube wall conductivity, W/(m K), default 45'}
  R_f_tube_m2K_W: {type: number, description: 'tube-side fouling, m2 K/W, default 0'}
  roughness_m: {type: number, description: 'tube roughness, m, default 4.5e-5'}
  air_T_K: {type: number, description: 'ambient air temperature, K'}
  air_P_Pa: {type: number, description: 'ambient pressure, Pa, default 101325'}
  air_mass_flow_kg_s: {type: number, description: 'total air mass flow, kg/s'}
  air_composition: {type: object, description: 'air mole fractions, default N2 0.79 / O2 0.21'}
  fan_efficiency: {type: number, description: 'total fan efficiency, (0, 1]'}
  allow_extrapolation: {type: boolean, description: 'permit Briggs-Young outside 1000 < Re < 8000'}
```

## Outputs
- **Port:** `outlet`.
- **`duty_W`:** F·(h_out − h_in), negative when cooling. **`power_W`:** 0.
- **info:**
  - `Q_W` (heat to air, positive), `U_bare_W_m2K`, `A_bare_m2`, `A_total_m2`, `F_t`, `LMTD_K`;
  - `h_air_bare_W_m2K`, `fin_efficiency`, `Re_air`, `h_tube_W_m2K`, `Re_tube`;
  - `dP_tube_Pa`, `dP_air_Pa`, `fan_power_W`, `air_T_out_K`, `briggs_young_in_range`.

## Tests
- **Closed-form** (pure functions, independent numbers from `calc_air_cooler.py`; geometry inputs from `ac_geo.txt`, the 4-row example from ht's docstring). The geometry is:
  ```
  AirCooledExchanger(tube_rows=4, tube_passes=4, tubes_per_row=20, tube_length=3,
                     tube_diameter=0.0254, fin_thickness=0.000406, fin_density=1/0.002309,
                     pitch_normal=0.06033, pitch_parallel=0.05207, fin_height=0.0159,
                     tube_thickness=0.0034, corbels=True)
  ```
  1. **Air side:** ṁ 8 kg/s, ρ 1.1584, cp 1007, μ 1.84e-5, k 0.0263, k_fin 205.
     - Expect V_max = 3.9232181, Re = 6273.601, Pr = 0.70451711, Nu = 35.8262065.
     - Expect h_fin = 37.095639, η_f = 0.899561982, h on the total-area basis = 33.499866, h_bare = 791.049477 W/m²K (rel 1e-8).
  2. **ESDU ΔP:** K_f = 1.32197789, K_a = 1.22509253, ΔP_air = 58.0623768 Pa; fan power at η 0.7 = 572.833235 W.
  3. **Range refusal:** ṁ 30 kg/s gives Re = 23526.0038, which must raise `BriggsYoungRangeError` without `allow_extrapolation`. With it, h_bare = 1713.45968 and ΔP = 635.02632 Pa.
- **Identity:** R1 → R0 as above, on `example_case`: the slice E-101 gas (R0 example feed, 322.15 K, 7 MPa) cooled by 308.15 K air, using the geometry above with tubes_per_row and ṁ_air chosen so Re_air is in range.
- **Refusals:** one per table row, including (tube_passes 3, rows 4), which is unsupported.
- **V1 candidates:**
  - GPSA *Engineering Data Book*, Section 10 (air-cooled exchangers), example of rating a bundle;
  - Serth & Lestina, *Process Heat Transfer*, 2nd ed., Ch. 12 (air-cooled heat exchangers), worked examples that print the geometry, h_air, U and ΔP_air.
  - If neither is accessible: record a "V1 gap: searched GPSA EDB Sec. 10, Serth 2nd ed. Ch. 12, Kern & Kraus 1972 Ch. 12" in the row notes. Never invent numbers.

## Steps
1. Pure functions: a geometry builder (params → `AirCooledExchanger`, with the supported-pair check), air-side h (wrap `h_Briggs_Young`, with `fin_efficiency_Kern_Kraus` for info), ESDU ΔP and fan power, with closed-form tests 1–3 and the geometry refusals. Push.
2. The adapter: the air state, the tube side via `rating.duct_h`, the brentq Q solve with F_t, the range check, info and `example_case`; the identity and remaining refusals. Push.
3. The YAML `levels.R1`, the V1 case or gap, harness write-doc and `--audit` as separate runs. Push and request review.

## Review checklist
- h is used on the **bare** basis with A_bare (no double application of A_increase or fin efficiency).
- Unsupported (passes, rows) pairs are refused; there is no silent `Ft_aircooler` fallback.
- Fan power goes in info, not `power_W`. The air side is not a port.
- The Briggs–Young range check is on the converged mean air Re.
- The brentq bracket is guarded at Q_max·(1 − 1e-9), with a non-finite F_t treated as infeasible.
