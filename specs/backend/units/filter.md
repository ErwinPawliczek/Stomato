# filter R1: Ruth constant-pressure cake filtration (area, cake thickness, cake moisture)

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/filter` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/filter_r1.py` (new): `FilterR1`, `FilterR1SpecError`, and the pure functions below
  - `tests/units/separation/test_filter_r1.py` (new)
  - `data/validation_units/separation/cases/filter.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `filter`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separation.filter.Filter` (R0) and `FilterSpecError`
  - `ngdesign.units.separation._util.stream_molar_mass(composition) -> float` (g/mol)
  - `ngdesign.contracts`; `Thermo`
- **Current state:**
  - R0 takes per-component `cake_fractions` (the spec), with `dP` on the filtrate. The cake leaves at P_in.
  - The example is water with 2 mol % SiO2, all of it to the cake.
  - On `pr`, SiO2 flashes as a "liquid" with ρ = 1451 kg/m³ (real silica is about 2650), so solid density is a required param.

## Method
### Equations (SI)
Sources: Ruth (1935); McCabe, Smith & Harriott, *Unit Operations of Chemical Engineering*, 7th ed., Ch. 29 (cake filtration); Geankoplis, 4th ed., §14.2.
- **F1 Constant-pressure Ruth equation:** `t_f = a·v² + b·v`, with `v = V/A` the filtrate volume per area in one cycle.
  - `a = μ·α·c/(2·ΔP)` and `b = μ·R_m/ΔP`.
  - α is the specific cake resistance (m/kg), R_m the medium resistance (1/m), μ the filtrate viscosity, ΔP the filtration pressure difference (the R0 `dP`, here required > 0).
  - c is the dry-cake mass per filtrate volume (kg/m³).
- **F2 Per-area volume:** `v = (−b + sqrt(b² + 4·a·t_f))/(2a)`.
- **F3 Required area:** `A_req = V_cycle/v`, with `V_cycle = Q_f·(t_f + t_d)` and t_d the downtime (washing, discharge).
- **F4 Cake thickness:** `L_cake = c·V_cycle/(A·ρ_s·(1 − ε))`, at `A = area_m2` if given, else `A_req`.
- **F5 Cake moisture:** liquid held in the cake voids, as a volumetric rate `q_ret = ε/(1−ε)·ṁ_s/ρ_s`.
- **F6 Concentration:** `c = ṁ_s/Q_f`.
  - `ṁ_s` is the mass flow of the cake components (`cake_fractions` × feed).
  - `Q_f` is the volumetric flow of the **R1 filtrate**, after moisture retention.
- **F7 Capacity ratio** when `area_m2` is given: `area_m2/A_req`. Below 1 means the filter is undersized for this feed; that is reported, not refused.

### Algorithm
1. Validate (refusal table). `dP > 0` is required at R1.
2. Run the R0 split with the user's `cake_fractions` and `dP` to get the dry split:
   - `r0 = Filter().solve(inlets, {"cake_fractions": ..., "dP": dP}, thermo)`;
   - `ṁ_s` is the R0 cake's mass flow when only cake components are in it;
   - filtrate liquid properties (ρ_L, μ_L) come from the R0 filtrate's largest-volume liquid phase, with `filtrate_viscosity_Pa_s` overriding a None viscosity.
3. Moisture (F5): `q_ret` m³/s of filtrate-composition liquid stays in the cake.
   - Molar rate: `n_ret = q_ret·ρ_L/(MW_filtrate/1000)`, using the R0 filtrate composition.
   - The fraction of each **non-cake** component sent to the cake is `f_m = n_ret/n_filtrate,R0`, the same for every filtrate component because the composition is shared. If `f_m > 1`, refuse: the cake cannot hold more liquid than there is.
4. R1 split: `fractions = cake_fractions` for the cake components, `f_m` for every other component. Then `r1 = Filter().solve(inlets, {"cake_fractions": fractions, "dP": dP}, thermo)`.
5. `Q_f = r1 filtrate mass_flow/ρ_L`. Then F6, F1–F4, and F7.
6. Return r1's outlets and duty, with `info` added.

### Reduction to the lower level
`cake_porosity = 0` (dry cake) gives `f_m = 0`: R1's outlets equal R0's with the user's `cake_fractions`, exactly. The sizing info is still reported.

### Refusals (`FilterR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `dP` missing or ≤ 0 | `dP` |
| α ≤ 0, R_m < 0, `t_filtration_s` ≤ 0, `t_down_s` < 0 | the parameter name |
| `solid_density_kg_m3` ≤ 0 or missing | `solid_density_kg_m3` |
| `cake_porosity` outside [0, 1) | `cake_porosity` |
| `area_m2` ≤ 0 | `area_m2` |
| `f_m > 1` | `moisture` |
| no cake component has positive flow | `cake_fractions` |
| filtrate viscosity unavailable | `filtrate_viscosity_Pa_s` |

R0's `FilterSpecError` propagates.

## Params
| name | type | unit | required/default | meaning |
|---|---|---|---|---|
| cake_fractions | object | – | required | as R0 (solids to the cake) |
| dP | number | Pa | required, > 0 | filtration ΔP |
| specific_cake_resistance_m_kg | number | m/kg | required | α |
| medium_resistance_1_m | number | 1/m | 0 | R_m |
| t_filtration_s | number | s | required | filtering time per cycle |
| t_down_s | number | s | 0 | wash and discharge time per cycle |
| solid_density_kg_m3 | number | kg/m³ | required | ρ_s |
| cake_porosity | number | – | 0 | ε |
| area_m2 | number | m² | absent | installed area, for the capacity ratio |
| filtrate_viscosity_Pa_s | number | Pa·s | phase value | override |

```yaml
type: object
required: [cake_fractions, dP, specific_cake_resistance_m_kg, t_filtration_s, solid_density_kg_m3]
properties:
  cake_fractions: {type: object, description: 'component id to the fraction of its molar flow sent to the cake (the solids)'}
  dP: {type: number, exclusiveMinimum: 0, description: 'filtration pressure difference, Pa; applied to the filtrate'}
  specific_cake_resistance_m_kg: {type: number, exclusiveMinimum: 0, description: 'specific cake resistance alpha, m/kg'}
  medium_resistance_1_m: {type: number, minimum: 0, description: 'filter medium resistance Rm, 1/m; default 0'}
  t_filtration_s: {type: number, exclusiveMinimum: 0, description: 'filtration time per cycle, s'}
  t_down_s: {type: number, minimum: 0, description: 'washing/discharge downtime per cycle, s; default 0'}
  solid_density_kg_m3: {type: number, exclusiveMinimum: 0, description: 'true solid density, kg/m3'}
  cake_porosity: {type: number, minimum: 0, exclusiveMaximum: 1, description: 'cake void fraction; default 0 (dry cake)'}
  area_m2: {type: number, exclusiveMinimum: 0, description: 'installed filter area, m2 (capacity ratio)'}
  filtrate_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'filtrate viscosity override, Pa s'}
```

## Outputs
- **Ports:** `filtrate` and `cake`, from R0 with the R1 fractions.
- **`info`:** `c_kg_m3`, `V_cycle_m3`, `v_per_area_m`, `A_required_m2`, `cake_thickness_m`, `retained_liquid_m3_s`, `moisture_fraction` (f_m), `capacity_ratio` (only with `area_m2`).

## Tests
Numbers come from `scratchpad/unit-specs/calc_filter.py`.
- **CF1**, through the pure function `ruth_area(mu, alpha, c, dP, Rm, t_f, V_cycle)`, with μ = 8.937e-4, α = 1e11, R_m = 1e10, ΔP = 1e5, ṁ_s = 0.10 kg/s, Q_f = 2.0e-3 m³/s, t_f = 600 s, t_d = 300 s:
  - `c = 50`, `V = 1.8`, `a = 22342.5`, `b = 89.37`;
  - `v = 0.161886086`, `A_req = 11.1189296 m²`;
  - rtol 1e-9.
- **CF2:** A = 10 → `capacity_ratio = 0.899367145`; rtol 1e-9.
- **CF3:** ρ_s = 2650 and ε = 0.4 → `L_cake = 5.09075742e-3 m` at A_req; rtol 1e-9.
- **CF4:** `q_ret = 2.51572327e-5 m³/s`, which is a fraction `0.0125786164` of 2.0e-3 m³/s; rtol 1e-9.
- **Identity:** on the R0 example feed (`cake_fractions {"SiO2": 1.0}`, `dP` 3e4), with `cake_porosity` 0 plus the sizing params: the outlets must be `==` R0's.
- **Moisture:** the same feed with ε = 0.4.
  - Every H2O and SiO2 flow in the cake: assert `cake H2O flow == f_m·R0 filtrate H2O flow` to 1e-12 relative.
  - Assert `info.moisture_fraction == f_m`, with f_m recomputed in the test from F5 and the R0 outlets' properties.
  - Balances: moles at 1e-12, energy at 1e-8.
- **Refusals:** one test per row. For the moisture refusal (`f_m > 1`), use ε = 0.99 with a 50 mol % solids slurry.
- **V1 candidates:**
  - Geankoplis, 4th ed., §14.2, Example 14.2-1: it evaluates α and R_m from constant-pressure data, then a later example computes the filtration time at given constants. Transcribe the printed inputs and the printed time or area.
  - McCabe-Smith-Harriott, 7th ed., Ch. 29, the worked constant-pressure example.
  - The FOSSEE open transcription (tbc-python.fossee.in, Geankoplis chapter 14) can corroborate the printed numbers, as was done for the membrane case.
  - If none can be verified: V1 gap naming them.

## Steps
1. Pure functions F1–F7 plus CF1–CF4. Push, then open the PR.
2. The `FilterR1` adapter, with the identity, moisture and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.filter_r1:FilterR1`). Regenerate the docs, then `--audit`. Push.
3. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- The quadratic root is the positive one.
- c uses the R1 filtrate volume.
- Moisture moves filtrate-composition liquid only.
- Solid density is a param, never a phase value.
- ε = 0 is exactly R0.
- The material split is delegated to R0.
