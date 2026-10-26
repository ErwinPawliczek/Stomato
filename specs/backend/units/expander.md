# expander R1: performance map (efficiency vs velocity ratio u/c₀, plus a flow-capacity range)

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit spec.
- **Wave/order:** parallel-safe
- **Branch:** `u-lv/expander` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/expander_r1.py` (new)
  - `tests/units/flow/test_expander_r1.py` (new)
  - `data/validation_units/flow/cases/expander.yaml` (new; only if a V1 case is found)
  - in `data/unit_models/flow.yaml`: the `levels.R1` entry of row `expander` (and the row `notes` line for a V1 gap)
- **Read-only imports (verified to exist, with signatures):**
  - `ngdesign.units.expander.Expander`: the R0 adapter, `Expander().solve(inlets, params, thermo) -> UnitResult`, params `P_out` (Pa) and `eta_isentropic`; ports `gas_in` → `gas_out`
  - `Thermo.flash_ps(z, P, S, molar_flow) -> StreamState`
  - `StreamState.mass_flow`; `Phase.density`
  - `scipy.interpolate.PchipInterpolator(x, y, axis=0, extrapolate=None)` (scipy 1.18.1)
- **Current state:** the R0 adapter `ngdesign.units.expander:Expander` has ports `gas_in` → `gas_out`.
  - Params: `P_out` (required, < P_in) and `eta_isentropic` (default 0.80).
  - h₂ = h₁ − η·(h₁ − h₂s); outlet = `flash_ph`; `power_W` = F·(h₂ − h₁) < 0.
  - info: `power_recovered_w`, `T_out`, `T_out_isentropic`, and the phase mole fractions.
  - It refuses a liquid inlet (vf < 0.999).

## Method
### Equations
1. Isentropic enthalpy drop per unit mass: Δh_s = (h₁ − h(P₂, s₁))/M (J/kg), with M = ṁ/F.
2. Spouting (isentropic jet) velocity: c₀ = √(2·Δh_s) (m/s).
3. Rotor tip speed: u = π·D·N/60 (m/s), with D the rotor tip diameter (m) and N the speed (rpm).
4. Velocity ratio: ν = u/c₀ (dimensionless).
   - Radial-inflow turbines peak near ν ≈ 0.7. The map gives η_s(ν) directly as data.
   - Sources: Whitfield & Baines, *Design of Radial Turbomachines* (1990), ch. 7, η vs U/C₀; Balje, *Turbomachines* (1981), ch. 3; Perry's 9th ed. §10, expanders.
5. Efficiency: η = η_map(ν), PCHIP with no extrapolation.
6. Optional flow-capacity range: the actual inlet volumetric flow Q = ṁ/ρ₁ must lie in [`flow_min_m3_s`, `flow_max_m3_s`] when either is given. Below the minimum, the nozzle setting cannot pass it; above the maximum, the machine chokes.
7. Outlet: R0 with `{"P_out": P₂, "eta_isentropic": η}`. R1 delegates, so the outlet, power and balance are R0's.

### Algorithm
1. Validate the inlet and params. The inlet must be vapour (vf ≥ 0.999).
2. If either flow limit is given, compute Q and check it; out of range raises `ExpanderFlowRangeError`.
3. `iso = thermo.flash_ps(z, P_out, s₁, F)`. Compute Δh_s; if Δh_s ≤ 0, raise. Then compute c₀, u and ν.
4. If ν is outside [ν_min, ν_max] of the map, raise `ExpanderMapRangeError`. Otherwise evaluate η; if η ∉ (0, 1], raise.
5. `r0 = Expander().solve(inlets, {"P_out": P_out, "eta_isentropic": η}, thermo)`.
6. Return r0's outlets, duty and power, with info = r0.info plus the R1 keys.

There is no iteration. The extra flash_ps in step 3 is repeated inside R0. That costs one flash; accept it, so that R0 stays the single owner of the outlet arithmetic.

### Reduction to the lower level
- A flat map with η constant = η* is R0 with `eta_isentropic = η*`.
- For any map, R1 equals `Expander().solve(inlets, {"P_out": P_out, "eta_isentropic": info["eta"]}, thermo)` exactly (`==`).

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| inlet vf < 0.999 | `ExpanderR1SpecError` | `inlet has liquid` |
| `P_out` missing, or ≥ P_in, or ≤ 0 | `ExpanderR1SpecError` | `P_out` |
| `rotor_diameter_m` ≤ 0 or `speed_rpm` ≤ 0 | `ExpanderR1SpecError` | the param name |
| `map.velocity_ratio` / `map.efficiency` missing, unequal, fewer than 2 points, or not strictly increasing | `ExpanderR1SpecError` | `map.velocity_ratio` |
| ν outside the map | `ExpanderMapRangeError(ExpanderR1SpecError)` | `velocity ratio` |
| η ∉ (0, 1] | `ExpanderR1SpecError` | `efficiency` |
| flow limits inconsistent (min ≥ max, or ≤ 0) | `ExpanderR1SpecError` | `flow_min_m3_s` |
| Q outside [min, max] | `ExpanderFlowRangeError(ExpanderR1SpecError)` | `flow` |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `P_out` | number | Pa | required | 0 < P_out < P_in | discharge pressure (set downstream, as in R0) |
| `rotor_diameter_m` | number | m | required | > 0 | rotor tip diameter |
| `speed_rpm` | number | rpm | required | > 0 | shaft speed |
| `map.velocity_ratio` | number[] | – | required | strictly increasing, ≥ 2 | u/c₀ points |
| `map.efficiency` | number[] | – | required | (0, 1] | isentropic efficiency at each point |
| `flow_min_m3_s` | number | m³/s | optional | > 0 | minimum actual inlet flow |
| `flow_max_m3_s` | number | m³/s | optional | > min | maximum actual inlet flow |

```yaml
    R1:
      status: provisional
      adapter: ngdesign.units.flow.expander_r1:ExpanderR1
      params:
        type: object
        required: [P_out, rotor_diameter_m, speed_rpm, map]
        properties:
          P_out: {type: number, description: 'outlet pressure, Pa'}
          rotor_diameter_m: {type: number, description: 'rotor tip diameter, m'}
          speed_rpm: {type: number, description: 'shaft speed, rpm'}
          map:
            type: object
            required: [velocity_ratio, efficiency]
            properties:
              velocity_ratio: {type: array, items: {type: number}, description: 'u/c0 points, strictly increasing'}
              efficiency: {type: array, items: {type: number}, description: 'isentropic efficiency at each point, (0, 1]'}
          flow_min_m3_s: {type: number, description: 'minimum actual inlet flow, m3/s (optional)'}
          flow_max_m3_s: {type: number, description: 'maximum actual inlet flow, m3/s (optional)'}
      note: performance map — isentropic efficiency vs velocity ratio u/c0 (PCHIP), flow-capacity range
      validation: []
      end_state: true
```

## Outputs
- Port `gas_out`: from R0.
- `duty_W = 0`; `power_W` < 0 (recovered), from R0.
- info: R0 keys, plus `eta`, `velocity_ratio`, `spouting_velocity_m_s`, `tip_speed_m_s`, `dh_isentropic_J_kg` and `Q_actual_m3_s`.

## Tests
Inlet for every test: the R0 example feed, `Expander.example_case()` (dry gas, 322.15 K, 7.0 MPa → P_out 2.0 MPa), flashed with `pr`. Independent script: `scratchpad/unit-specs/calc_expander.py`.
- **Closed-form:** D = 0.30 m, N = 20000 rpm; map `velocity_ratio = [0.40, 0.50, 0.60, 0.70, 0.80]`, `efficiency = [0.58, 0.65, 0.72, 0.79, 0.86]` (linear test data: η = 0.30 + 0.70·ν).
  - M = 0.0201670784 kg/mol; Δh_s = **125823.613 J/kg**; c₀ = **501.644521 m/s**; u = **314.159265 m/s**; ν = **0.626258739**.
  - η = **0.738381118**; T_out = **264.634943 K**; power_W = **−1296007.11 W**; outlet vf = 0.973902259 (two-phase outlet, allowed as in R0).
  - Tolerances: rel 1e-9 on ν and η; rel 1e-7 on T and power.
- **Identity:** `==` against `Expander().solve(inlets, {"P_out": 2.0e6, "eta_isentropic": info["eta"]}, thermo)`. Also a flat map at 0.80 equals R0's own example result.
- **Refusals:** one test per row.
  - `speed_rpm = 10000` gives ν = 0.313 < 0.40, which is outside the map.
  - `flow_max_m3_s = 0.1` with Q = **0.222477211 m³/s** (ṁ/ρ of the flashed inlet) raises the flow-range error.
  - `flow_min_m3_s = 0.2, flow_max_m3_s = 0.3` passes.
- **V1 candidates:**
  - **V1 gap.** No open example known to the spec author prints a full u/c₀ map plus the inlet state and the resulting outlet. **Search:**
    - Whitfield & Baines 1990, ch. 7 examples;
    - Perry's 9th ed. §10 expander example;
    - GPSA Section 13 turboexpander example (citation only; verify that inputs and results are printed);
    - Campbell, *Gas Conditioning and Processing* vol. 2, expander chapter.

## Steps (each at most about 40 minutes, each ending in a push)
1. Create `expander_r1.py`: the errors, params, the Δh_s/c₀/u/ν chain, the PCHIP map with its range refusal, and delegation to R0. Add the closed-form, identity and map/param refusal tests. Push, then open the PR.
2. Add the flow-capacity range (eq. 6) with its tests, the catalogue `levels.R1` (YAML above), the V1 case or the recorded gap, the docs regeneration and the gates. Push.

## Review checklist (for the orchestrator)
- c₀ = √(2·Δh_s), with Δh_s per kg (divided by M). u = π·D·N/60.
- The efficiency map is read at u/c₀ with no extrapolation and an explicit range check.
- R1 delegates the outlet to `Expander().solve`, with an `==` identity test.
- Signs: Δh_s > 0, and `power_W` < 0, as R0 returns it.
- No edits to `units/expander.py`; only the `expander` row's `levels.R1` changes in YAML.
