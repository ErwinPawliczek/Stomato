# fan R1: performance curve (pressure rise and efficiency vs flow) with fan laws and density correction

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit spec.
- **Wave/order:** parallel-safe
- **Branch:** `u-lv/fan` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/fan_r1.py` (new)
  - `tests/units/flow/test_fan_r1.py` (new)
  - `data/validation_units/flow/cases/fan.yaml` (new; only if a V1 case is found)
  - in `data/unit_models/flow.yaml`: the `levels.R1` entry of row `fan` (and the row `notes` line for a V1 gap)
- **Read-only imports (verified to exist, with signatures):**
  - `ngdesign.units.flow.fan.Fan`: the R0 adapter, `Fan().solve(inlets, params, thermo) -> UnitResult`, params `dP` (Pa, > 0) and `eta` (default 0.7)
  - `ngdesign.units.flow.fan.FanSpecError` (`ValueError`)
  - `StreamState.mass_flow`; `Phase.density`
  - `scipy.interpolate.PchipInterpolator(x, y, axis=0, extrapolate=None)` (scipy 1.18.1)
- **Current state:** the R0 adapter `ngdesign.units.flow.fan:Fan` has ports `inlet` → `outlet`.
  - Params: `dP` (required) and `eta`.
  - It makes one `isentropic_step(inlet, P_in + dP, eta, thermo, "compress")`; `power_W` > 0.
  - info: `pressure_ratio`. It refuses a non-gas inlet with `FanSpecError`.

## Method
### Equations
1. Actual inlet volumetric flow: Q = ṁ/ρ₁, with ρ₁ the density of the single gas phase.
2. Fan laws (AMCA Publication 201, *Fans and Systems*; ASHRAE Handbook – HVAC Systems and Equipment, ch. "Fans", fan laws), at speed ratio s = N/N_curve and density ratio r = ρ₁/ρ_curve:
   - Q_eq = Q/s;
   - Δp(Q) = Δp_c(Q_eq)·s²·r;
   - η(Q) = η_c(Q_eq).
   - When `curve_density_kg_m3` is omitted, r = 1, meaning the curve is taken at the operating density.
3. Curve: PCHIP over `flow_m3_s`, with no extrapolation.
4. The pressure rise is the fan total pressure rise, applied as the stream static pressure change (P_out = P_in + Δp). This matches R0, which carries no velocity head. State this in the docstring.
5. Outlet and power: R0 with `{"dP": Δp, "eta": η}`.

### Algorithm
1. Validate the inlet and params. The gas check is R0's own, reached through delegation, but R1 checks vf < 0.999 first and raises `FanR1SpecError`, so the refusal names R1.
2. Compute Q and Q_eq. If out of range, raise `FanCurveRangeError`.
3. Evaluate Δp and η. If Δp ≤ 0 or η ∉ (0, 1], raise.
4. `r0 = Fan().solve(inlets, {"dP": Δp, "eta": η}, thermo)`.
5. Return r0's outlets and power, with info = r0.info plus the R1 keys.

There is no iteration.

### Reduction to the lower level
- A flat curve (constant Δp*, η*) with s = 1 and r = 1 is R0 with `dP = Δp*` and `eta = η*`.
- For any curve, R1 equals `Fan().solve(inlets, {"dP": info["dP_Pa"], "eta": info["eta"]}, thermo)` exactly (`==`).

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| inlet vf < 0.999 | `FanR1SpecError` | `inlet is not gas` |
| `curve.flow_m3_s` / `pressure_rise_Pa` / `efficiency` missing, unequal, fewer than 2 points, or flow not strictly increasing | `FanR1SpecError` | `curve.<key>` |
| `speed_ratio` ≤ 0 | `FanR1SpecError` | `speed_ratio` |
| `curve_density_kg_m3` ≤ 0 | `FanR1SpecError` | `curve_density_kg_m3` |
| Q_eq outside the curve | `FanCurveRangeError(FanR1SpecError)` | `outside the curve` |
| Δp ≤ 0 or η ∉ (0, 1] | `FanR1SpecError` | `pressure rise` / `efficiency` |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `curve.flow_m3_s` | number[] | m³/s, actual inlet | required | strictly increasing, ≥ 2 | curve flows at curve speed |
| `curve.pressure_rise_Pa` | number[] | Pa | required | > 0 | fan total pressure rise |
| `curve.efficiency` | number[] | – | required | (0, 1] | fan (isentropic) efficiency |
| `speed_ratio` | number | – | 1.0 | > 0 | N/N_curve |
| `curve_density_kg_m3` | number | kg/m³ | omitted (r = 1) | > 0 | gas density the curve was rated at |

```yaml
    R1:
      status: provisional
      adapter: ngdesign.units.flow.fan_r1:FanR1
      params:
        type: object
        required: [curve]
        properties:
          curve:
            type: object
            required: [flow_m3_s, pressure_rise_Pa, efficiency]
            properties:
              flow_m3_s: {type: array, items: {type: number}, description: 'actual inlet flow points, m3/s, strictly increasing'}
              pressure_rise_Pa: {type: array, items: {type: number}, description: 'fan total pressure rise at each point, Pa'}
              efficiency: {type: array, items: {type: number}, description: 'efficiency at each point, (0, 1]'}
          speed_ratio: {type: number, description: 'N / N_curve (fan laws), default 1.0'}
          curve_density_kg_m3: {type: number, description: 'rating density of the curve, kg/m3; omitted = operating density'}
      note: performance curve (pressure rise/efficiency vs flow, PCHIP) with fan laws and density correction
      validation: []
      end_state: true
```

## Outputs
- Port `outlet`: from R0.
- `duty_W = 0`; `power_W` > 0, from R0.
- info: R0's `pressure_ratio`, plus `dP_Pa`, `eta`, `Q_actual_m3_s`, `Q_equiv_m3_s`, `speed_ratio` and `density_ratio`.

## Tests
Inlet for every test: the R0 example feed, `Fan.example_case()` (methane, 300 K, 1 bar, 50 mol/s), flashed with `pr`. Independent script: `scratchpad/unit-specs/calc_fan.py`.
- Measured inlet: ρ₁ = 0.644554842 kg/m³, ṁ = 0.802123 kg/s, Q = **1.24446044 m³/s**.
- **Curve** (linear data):
  - `flow_m3_s = [0.5, 0.75, 1.0, 1.25, 1.5]`
  - `pressure_rise_Pa = [6000, 5000, 4000, 3000, 2000]`
  - `efficiency = [0.60, 0.65, 0.70, 0.75, 0.80]`
- **Closed-form 1** (s = 1, no density correction):
  - Δp = 8000 − 4000·Q = **3022.15826 Pa**; η = 0.5 + 0.2·Q = **0.748892087**;
  - P_out = **103022.158 Pa**; T_out = **302.77891 K**; power_W = **4964.78391 W**.
  - Tolerances: rel 1e-9 on Δp and η; rel 1e-7 on T and power.
- **Closed-form 2** (s = 1.1, `curve_density_kg_m3 = 1.2`):
  - Q_eq = **1.13132767**; Δp = (8000 − 4000·Q_eq)·1.21·(0.644554842/1.2) = **2258.29139 Pa**; η = **0.726265534**;
  - P_out = **102258.291 Pa**; T_out = **302.14774 K**; power_W = **3836.49333 W**.
- **Identity:** `==` against `Fan().solve(inlets, {"dP": info["dP_Pa"], "eta": info["eta"]}, thermo)`. Also a flat curve (Δp 5000, η 0.7) equals R0's own example result.
- **Refusals:** one per row. `speed_ratio = 0.5` gives Q_eq = 2.49 > 1.5, which is outside the curve.
- **V1 candidates:**
  - **V1 gap. Search:**
    - AMCA 201 (fan-law worked examples);
    - ASHRAE Handbook HVAC Systems & Equipment, Fans chapter, examples;
    - Perry's 9th ed. §10 (fans and blowers).
  - A fan-law example prints inputs and results, so it would qualify if the harness can feed the same gas state. Otherwise record the gap.

## Steps (each at most about 40 minutes, each ending in a push)
1. Create `fan_r1.py`: the errors, params, PCHIP plus fan laws plus density ratio, the range refusal, and delegation to R0. Add both closed-form tests, the identity test and the refusal tests. Push, then open the PR.
2. Add the catalogue `levels.R1` (YAML above), the V1 case or the recorded gap, the docs regeneration and the gates. Push.

## Review checklist (for the orchestrator)
- Fan laws: Q ∝ s, Δp ∝ s²·(ρ/ρ_curve), and η unchanged at Q_eq.
- Δp is applied as P_out = P_in + Δp through R0 (the documented total-pressure-as-static choice).
- PCHIP has no extrapolation, and an explicit range refusal comes first.
- R1 delegates to `Fan().solve`, with an `==` identity test.
- No edits to `units/flow/fan.py`; only the `fan` row's `levels.R1` changes in YAML.
