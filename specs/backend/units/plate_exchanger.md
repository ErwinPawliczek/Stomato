# plate_exchanger R1: gasketed chevron-plate rating (Martin, VDI Heat Atlas N6)

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional` (`end_state: true` stays on R1).
- **Depends on:**
  - the U-R2 conventions, U-01d (#243) and **T-PP** (`phase_props` transport properties);
  - **double_pipe R1 merged** (it imports `ngdesign.units.heat.rating`).
- **Wave/order:** after double_pipe; parallel with shell_tube and air_cooler.
- **Branch:** `u-lv/plate_exchanger` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/plate_exchanger_r1.py` (new; `PlateExchangerR1` plus pure functions);
  - `tests/units/heat/test_plate_exchanger_r1.py` (new);
  - `data/validation_units/heat/cases/plate_exchanger.yaml` (new);
  - the `levels.R1` entry of row `plate_exchanger` in `data/unit_models/heat.yaml`, plus the row `notes`.
  - `units/heat/exchangers.py` (R0) is NOT edited.
- **Read-only imports (verified, `ht` 1.2.0 / `fluids` 1.3.1):**
  - `fluids.geometry.PlateExchanger(amplitude, wavelength, chevron_angle=45, chevron_angles=None, width=None, length=None, thickness=None, d_port=None, plates=None)`. It exposes `D_hydraulic`, `A_channel_flow` (= b·width per channel), `channels_per_fluid`, `A_heat_transfer`, `plate_enlargement_factor`, `b`, `chevron_angle` and `length`.
  - `ht.Nu_plate_Martin(Re, Pr, chevron_angle, variant='VDI') -> float`. **Use `variant='VDI'`.** The `'1999'` variant's friction formula is documented on a Fanning basis while the 0.122 Nusselt coefficient assumes Darcy, so do not mix them.
  - `fluids.friction_plate_Martin_VDI(Re, chevron_angle) -> float` (Darcy). **Its docstring misprints the turbulent f₀** as (1.56 ln Re − 3)⁻². The code uses Konakov's (1.8·log₁₀Re − 1.5)⁻², which is what VDI N6 prints. Verified: at Re 2500, 45°, code = 0.867587711, docstring formula = 0.787101468. Cite the VDI form.
  - `ht.Nu_plate_Kumar(Re, Pr, chevron_angle, mu=None, mu_wall=None)` and `fluids.friction_plate_Kumar(Re, chevron_angle)` (optional correlation for V1 fidelity)
  - `ht.effectiveness_from_NTU(NTU, Cr, subtype='counterflow')`
  - `ngdesign.units.heat.rating`: `film_props`, `inlet_kind`, `rate_two_stream`, the errors
- **Current state:**
  - R0 is `ngdesign.units.heat.exchangers:PlateExchanger`: ports `hot_in`/`cold_in` → `hot_out`/`cold_out`, `two_stream` specs, info `duty_W`, `LMTD_K`, `lmtd_valid`, `min_approach_K`, `UA_W_K`.
  - No V1 (the row notes record the searches).

## Method

### Equations
Martin 1996, Chem. Eng. Process. 35:301; VDI Heat Atlas 2nd ed. (2010), N6.
1. **Geometry** from `fluids.geometry.PlateExchanger`:
   - b = 2·amplitude;
   - D_h = 2b/φ, where φ is the plate enlargement factor;
   - per-channel flow area A_ch = b·width;
   - channels per fluid N_ch = (plates − 1)/2;
   - heat-transfer area A = `A_heat_transfer`.
   - Single-pass, counter-current arrangement.
2. **Channel flow:** v = ṁ/(ρ·N_ch·A_ch), Re = ρvD_h/μ, Pr = cp_mass·μ/k.
3. **Friction (Darcy, VDI N6):** 1/√f = cos φ_c/√(0.18 tan φ_c + 0.36 sin φ_c + f₀/cos φ_c) + (1 − cos φ_c)/√(3.8 f₁).
   - Re < 2000: f₀ = 64/Re and f₁ = 597/Re + 3.85.
   - Otherwise: f₀ = (1.8 log₁₀Re − 1.5)⁻² and f₁ = 39·Re^−0.289.
   - φ_c is the chevron angle measured from the flow direction.
4. **Nusselt (VDI N6):** Nu = 0.122·Pr^⅓·(μ/μ_w)^⅙·[f·Re²·sin 2φ_c]^0.374, with (μ/μ_w) = 1 at R1, stated. Then h = Nu·k/D_h.
5. **U** = 1/(1/h_h + t_p/k_p + 1/h_c + R_f,h + R_f,c), on the plate area A.
6. **ΔP per fluid:** ΔP = f(L_p/D_h)ρv²/2 + 1.4·ρv_port²/2.
   - L_p = the port-to-port length (`length`);
   - v_port = ṁ/(ρπd_port²/4);
   - the port loss is 1.4 velocity heads (Shah & Focke 1988; Kakaç, Liu & Pramuanjaroenkij, 3rd ed., Ch. 10).
7. **Thermal:** counterflow ε-NTU, through `rating.rate_two_stream` with `eps_of` = counterflow.

### Algorithm
1. Validate the params and build the geometry. Both inlets must be single phase and flowing, with T_h,in > T_c,in.
2. ΔP for each side from inlet properties (Eq. 6), then the outlet pressures.
3. `rating.rate_two_stream(hot, cold, thermo, P_h_out, P_c_out, ua_of, eps_of)`. `ua_of` evaluates both films at the side means via Eqs. 2–4 and returns U·A.
4. If `correlation == "kumar"`, Eqs. 3–4 use `fluids.friction_plate_Kumar` and `ht.Nu_plate_Kumar`. This option exists only so a V1 case can run the book's own correlation.
5. **Range check:** Martin's data cover 200 ≤ Re ≤ 10⁴. Outside that, raise `PlateCorrelationRangeError`, unless `allow_extrapolation`; then flag `info["correlation_in_range"] = 0.0`.
6. `UnitResult` follows the R0 convention: `duty_W` = Σ out − Σ in (round-off); the transferred heat goes in info.

### Reduction to the lower level
R0 (`two_stream` with `duty_W` = R1's info `duty_W`, `dP_hot`/`dP_cold` = R1's ΔP) reproduces both R1 outlets to 1e-10 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| geometry missing or ≤ 0; plates < 3; chevron angle outside [0, 80] | `PlateGeometryError(ValueError)` | the param name |
| `correlation` ∉ {martin, kumar} | `PlateGeometryError` | "correlation" |
| a zero-flow side | `RatingError` | "needs both streams flowing" |
| T_h,in ≤ T_c,in | `TemperatureCross` | "inlet temperatures" |
| a phase change | `SinglePhaseRequired` | "R1 rates single-phase duty" |
| Re outside [200, 1e4] without `allow_extrapolation` | `PlateCorrelationRangeError(RatingError)` | "Re" + side |
| missing transport properties | `PropertyUnavailable` | the property |
| no convergence | `RatingConvergenceError` | "did not converge" |

## Params
| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `amplitude_m` | number | m | required | > 0 | corrugation amplitude a (b = 2a) |
| `wavelength_m` | number | m | required | > 0 | corrugation pitch Λ |
| `chevron_angle_deg` | number | deg | required | 0–80 | angle from the flow direction |
| `plate_width_m`, `plate_length_m` | number | m | required | > 0 | port-to-port flow width and length |
| `port_diameter_m` | number | m | required | > 0 | port diameter |
| `n_plates` | integer | – | required | ≥ 3 | total plates |
| `plate_thickness_m` | number | m | 6e-4 | > 0 | plate thickness |
| `k_plate_W_mK` | number | W/m/K | 16.0 | > 0 | plate conductivity (austenitic stainless) |
| `R_f_hot_m2K_W`, `R_f_cold_m2K_W` | number | m²K/W | 0.0 | ≥ 0 | fouling |
| `correlation` | string | – | martin | martin/kumar | h and f correlation |
| `allow_extrapolation` | boolean | – | false | – | permit use outside 200–1e4 |

```yaml
type: object
required: [amplitude_m, wavelength_m, chevron_angle_deg, plate_width_m, plate_length_m, port_diameter_m, n_plates]
properties:
  amplitude_m: {type: number, description: 'corrugation amplitude, m (channel gap = 2 x amplitude)'}
  wavelength_m: {type: number, description: 'corrugation wavelength, m'}
  chevron_angle_deg: {type: number, description: 'chevron angle from the flow direction, deg'}
  plate_width_m: {type: number, description: 'flow width, m'}
  plate_length_m: {type: number, description: 'port-to-port length, m'}
  port_diameter_m: {type: number, description: 'port diameter, m'}
  n_plates: {type: integer, description: 'total plate count'}
  plate_thickness_m: {type: number, description: 'plate thickness, m, default 6e-4'}
  k_plate_W_mK: {type: number, description: 'plate conductivity, W/(m K), default 16'}
  R_f_hot_m2K_W: {type: number, description: 'hot-side fouling, m2 K/W, default 0'}
  R_f_cold_m2K_W: {type: number, description: 'cold-side fouling, m2 K/W, default 0'}
  correlation: {type: string, enum: [martin, kumar], description: 'film/friction correlation, default martin'}
  allow_extrapolation: {type: boolean, description: 'permit 200 > Re or Re > 1e4'}
```

## Outputs
- **Ports:** `hot_out` and `cold_out`.
- **`duty_W`:** round-off residual. **`power_W`:** 0.
- **info:**
  - `duty_W` (hot → cold, W), `U_W_m2K`, `A_m2`, `UA_W_K`, `NTU`, `effectiveness`, `LMTD_K`;
  - `h_hot_W_m2K`, `h_cold_W_m2K`, `Re_hot`, `Re_cold`;
  - `dP_hot_Pa`, `dP_cold_Pa`, `correlation_in_range`.

## Tests
- **Closed-form** (pure functions, independent numbers from `calc_plate_exchanger.py`, rel 1e-8):
  - Geometry P1: a = 0.5 mm, Λ = 3.7 mm, 45°, width 0.3 m, length 1.2 m, port 0.05 m, 51 plates (25 channels per fluid, A_ch = 3.0e-4 m², D_h = 0.0017223766473078426 from `fluids.geometry`).
  1. **Laminar branch:** ṁ 3 kg/s, ρ 990, μ 6.0e-4, k 0.63, cp 4180.
     - Expect v = 0.404040404, Re = 1148.2511, Pr = 3.98095238, f = 0.892089304, Nu = 36.0342748, h = 13180.3884 W/m²K.
     - Channel ΔP = 50224.5717 Pa; port v = 1.54332066 m/s; port ΔP = 1650.61419 Pa.
  2. **Turbulent branch:** ṁ 8 kg/s, same fluid. Expect v = 1.07744108, Re = 3062.00293, f = 0.857073074, Nu = 73.9326645, h = 27042.6208.
  3. **Friction spot values:** f(500, 45°) = 1.06688451, f(500, 60°) = 2.3862954, f(2500, 45°) = 0.867587711, f(2500, 60°) = 1.94223808.
  4. **U:** with both h = 13180.3884, t_p 0.6 mm, k_p 16: U = 5284.2784.
- **Identity:** R1 → R0 on `example_case`: the R0 example (water 433.15 K / 303.15 K at 1 MPa, 100/150 mol/s) with geometry P1 at reduced plates so that Re is in range. Use `thermo: pr-peneloux`, or another volume-translated package that returns μ and k, because PR liquid water density is 836 kg/m³ instead of about 990.
- **Refusals:** one per table row.
- **V1 candidates:**
  - Kakaç, Liu & Pramuanjaroenkij, *Heat Exchangers*, 3rd ed., Ch. 10 (gasketed plate heat exchangers), worked rating examples (water–water) that print the plate geometry, h, U, duty and ΔP. They use Kumar's correlation, so run the case with `correlation: kumar`.
  - If not accessible: "V1 gap: searched Kakaç 3rd ed. Ch. 10, VDI Heat Atlas N6 examples, Wang/Sundén/Manglik *Plate Heat Exchangers* (2007) examples".

## Steps
1. Pure functions: the geometry builder, channel Re, friction (VDI form, explicit, with the Konakov branch), Nusselt (Martin VDI, plus the Kumar switch), U and ΔP with port loss; closed-form tests 1–4 and the geometry refusals. Push.
2. The adapter via `rating.rate_two_stream`, the range check, info, `example_case`; the identity and refusals. Push.
3. The YAML `levels.R1`, the V1 case or gap, harness runs. Push and request review.

## Review checklist
- The friction branch at Re = 2000 uses Konakov (1.8 log₁₀ Re − 1.5)⁻², and Martin is used with variant `'VDI'` consistently in h and ΔP.
- The velocity uses per-fluid channels and b·width. D_h comes from the geometry object.
- The port loss is 1.4 velocity heads, cited.
- The range refusal is present. R0 is untouched.
