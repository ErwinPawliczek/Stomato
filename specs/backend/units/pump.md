# pump R1: pump curve with affinity laws and an NPSHa check

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit spec.
- **Wave/order:** parallel-safe
- **Branch:** `u-lv/pump` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/pump_r1.py` (new)
  - `tests/units/flow/test_pump_r1.py` (new)
  - `data/validation_units/flow/cases/pump.yaml` (new; only if a V1 case is found)
  - in `data/unit_models/flow.yaml`: the `levels.R1` entry of row `pump` (and the row `notes` line for a V1 gap)
- **Read-only imports (verified to exist, with signatures):**
  - `ngdesign.units.pump.Pump`: the R0 adapter, `Pump().solve(inlets, params, thermo) -> UnitResult`, params `P_out` (Pa) and `eta`
  - `ngdesign.units.pump._liquid_density(state: StreamState) -> float` (density of the largest liquid phase, kg/m³)
  - `ngdesign.units.pump.G_STD = 9.80665`
  - `ngdesign.sizing.pump_power.npsh_available(P_suction_Pa, P_vapor_Pa, rho, static_head_m, friction_head_m) -> float` (m)
  - `Thermo.bubble_point(z, *, T=None, P=None) -> SaturationPoint` (fields `T`, `P`, `kind`, `incipient_composition`)
  - `scipy.interpolate.PchipInterpolator(x, y, axis=0, extrapolate=None)` (scipy 1.18.1 installed)
- **Current state:** the R0 adapter `ngdesign.units.pump:Pump` has ports `inlet` → `outlet`.
  - Params: `P_out` (required) and `eta` (default 0.65).
  - Q = mass_flow / ρ_liquid; shaft = Q·ΔP/η; h_out = h_in + shaft/F; outlet = `flash_ph(z, P_out, h_out, F)`; `power_W` = shaft.
  - info: `head_m`, `Q_m3_s`. It refuses a vapour inlet (vf > 0.001) with a plain `ValueError`.

## Method
### Equations
1. Inlet volumetric flow: Q = ṁ / ρ_L, with ρ_L from `_liquid_density(inlet)` (as in R0).
2. Affinity laws at speed ratio s = N/N_curve (Karassik et al., *Pump Handbook*, 4th ed., §2.1 affinity laws; Perry's 9th ed. §10, "Affinity laws"):
   - Q_eq = Q / s;
   - H(Q) = s²·H_c(Q_eq);
   - η(Q) = η_c(Q_eq), so efficiency is unchanged at the equivalent point;
   - NPSHr(Q) = s²·NPSHr_c(Q_eq). This is the usual approximation; state it in the module docstring.
3. Curve interpolation: H_c, η_c and NPSHr_c are monotone-piecewise-cubic (PCHIP) interpolants of the supplied points over `flow_m3_s`, with no extrapolation.
4. Pressure rise: ΔP = ρ_L·g·H, with g = 9.80665 m/s²; P_out = P_in + ΔP.
5. Thermodynamics: the outlet comes from the R0 adapter with `{"P_out": P_out, "eta": η}`. The R1 class calls `Pump().solve(...)`, so the outlet, `power_W = Q·ΔP/η` and the energy balance are R0's by construction.
6. Suction vapour pressure: P_v = `thermo.bubble_point(z, T=T_in).P`. For a mixture, the bubble-point pressure at suction temperature is the vapour pressure that sets cavitation.
7. NPSHa = (P_in − P_v)/(ρ_L·g) + z_s − h_f (Hydraulic Institute ANSI/HI 9.6.1; Perry's 9th ed. §10). Evaluate it with `npsh_available(inlet.P, P_v, ρ_L, static_head_m, friction_head_m)`.
8. NPSH margin: M = NPSHa − NPSHr(Q), in m. It is computed only when `npsh_required_m` is given.

### Algorithm
1. Validate the inlet and params (refusal table). The inlet must be liquid: vf ≤ 0.001, the same threshold as R0.
2. Compute ρ_L, Q (eq. 1) and Q_eq = Q / speed_ratio.
3. If Q_eq < flow_m3_s[0] or Q_eq > flow_m3_s[-1], refuse with `PumpCurveRangeError`. There is no extrapolation.
4. Build PCHIP interpolants (`extrapolate=False`). Evaluate H, η and NPSHr (eqs. 2–3). If η ∉ (0, 1] or H ≤ 0, refuse.
5. Compute ΔP and P_out (eq. 4).
6. `r0 = Pump().solve(inlets, {"P_out": P_out, "eta": η}, thermo)`.
7. Compute P_v, NPSHa and the margin (eqs. 6–8).
   - If `npsh_required_m` is given, M < 0 and `npsh_check == "refuse"`, raise `PumpCavitationError`, naming NPSHa and NPSHr.
   - With `npsh_check == "report"`, return the result with the negative margin in info.
8. Return `UnitResult(outlets=r0.outlets, duty_W=r0.duty_W, power_W=r0.power_W, info={**r0.info, ...R1 keys})`.

There is no iteration.

### Reduction to the lower level
- A curve with a constant head H* and constant efficiency η*, at `speed_ratio = 1`, is identical to R0 solved with P_out = P_in + ρ_L·g·H* and eta = η*.
- More strongly, for ANY curve, R1's `outlets`, `power_W` and `duty_W` equal `Pump().solve(inlets, {"P_out": info["P_out_Pa"], "eta": info["eta"]}, thermo)` exactly (`==`), because R1 delegates.
- The identity test asserts this to 0.0 difference on T, P, enthalpy and power.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| inlet vf > 0.001 | `PumpR1SpecError` | `inlet has vapor` |
| `curve` missing, or `flow_m3_s` / `head_m` missing | `PumpR1SpecError` | `curve.flow_m3_s` / `curve.head_m` |
| arrays of unequal length, fewer than 2 points, or flow not strictly increasing | `PumpR1SpecError` | `strictly increasing` / `same length` |
| neither `curve.efficiency` nor `eta` given, or both given | `PumpR1SpecError` | `exactly one of curve.efficiency or eta` |
| `speed_ratio` ≤ 0 | `PumpR1SpecError` | `speed_ratio` |
| Q_eq outside the curve | `PumpCurveRangeError(PumpR1SpecError)` | `outside the curve` |
| interpolated η ∉ (0, 1] or H ≤ 0 | `PumpR1SpecError` | `efficiency` / `head` |
| `npsh_required_m` length ≠ flow length | `PumpR1SpecError` | `npsh_required_m` |
| `npsh_check` not in {refuse, report} | `PumpR1SpecError` | `npsh_check` |
| NPSHa < NPSHr with `npsh_check = "refuse"` | `PumpCavitationError(PumpR1SpecError)` | `NPSHa` |

All of these are new classes in `pump_r1.py`, subclassing `ValueError`.

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `curve.flow_m3_s` | number[] | m³/s | required | strictly increasing, ≥ 2 points | curve flow points at the curve speed |
| `curve.head_m` | number[] | m | required | > 0 | head at each point |
| `curve.efficiency` | number[] | – | exactly one of this or `eta` | (0, 1] | pump efficiency at each point |
| `curve.npsh_required_m` | number[] | m | optional | ≥ 0 | NPSHr at each point |
| `eta` | number | – | exactly one of this or `curve.efficiency` | (0, 1] | constant efficiency |
| `speed_ratio` | number | – | 1.0 | > 0 | N / N_curve |
| `static_head_m` | number | m | 0.0 | any | liquid level above the suction (+) |
| `friction_head_m` | number | m | 0.0 | ≥ 0 | suction-line friction head |
| `npsh_check` | string | – | `"refuse"` | refuse / report | action on a negative NPSH margin |

```yaml
    R1:
      status: provisional
      adapter: ngdesign.units.flow.pump_r1:PumpR1
      params:
        type: object
        required: [curve]
        properties:
          curve:
            type: object
            required: [flow_m3_s, head_m]
            properties:
              flow_m3_s: {type: array, items: {type: number}, description: 'curve flow points, m3/s, strictly increasing'}
              head_m: {type: array, items: {type: number}, description: 'head at each flow point, m'}
              efficiency: {type: array, items: {type: number}, description: 'efficiency at each flow point, (0, 1]'}
              npsh_required_m: {type: array, items: {type: number}, description: 'NPSHr at each flow point, m'}
          eta: {type: number, description: 'constant efficiency when the curve has none, (0, 1]'}
          speed_ratio: {type: number, description: 'N / N_curve for the affinity laws, default 1.0'}
          static_head_m: {type: number, description: 'suction static head, m, default 0'}
          friction_head_m: {type: number, description: 'suction friction head, m, default 0'}
          npsh_check: {type: string, enum: [refuse, report], description: 'default refuse'}
      note: curve (head/efficiency vs flow, PCHIP, affinity laws) and NPSHa check
      validation: []
      end_state: true
```

## Outputs
- Port `outlet`: from R0, a PH flash at P_out.
- `duty_W = 0`; `power_W` = shaft power into the process (R0).
- info: R0's `head_m` and `Q_m3_s`, plus:
  - `P_out_Pa`, `eta`, `speed_ratio`, `Q_equiv_m3_s`;
  - `P_vapor_Pa`, `NPSHa_m`;
  - when NPSHr is given: `NPSHr_m` and `NPSH_margin_m`;
  - `curve_fraction`, defined as (Q_eq − Q_min)/(Q_max − Q_min) and dimensionless.

## Tests
Inlet for every test: the R0 example feed, `Pump.example_case()` (293.15 K, 1.0 MPa, 5 mol/s condensate blend), flashed with `pr`. Independent script: `scratchpad/unit-specs/calc_pump.py`.
- Measured inlet: ρ_L = 598.62109 kg/m³, ṁ = 0.287104355 kg/s, Q = 4.79609489e-4 m³/s.
- **Curve** (linear data, which PCHIP reproduces exactly):
  - `flow_m3_s = [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4]`
  - `head_m = [80.0, 72.0, 64.0, 56.0, 48.0]`
  - `efficiency = [0.40, 0.50, 0.60, 0.70, 0.80]`
- **Closed-form 1** (speed_ratio 1):
  - H = 80 − 40000·Q = **60.8156204 m**; η = 0.40 + 500·Q = **0.639804745**;
  - ΔP = ρ·g·H = **357016.124 Pa**, so P_out = **1357016.12 Pa**;
  - shaft = Q·ΔP/η = **267.6259 W**.
  - Tolerance: rel 1e-9 on P_out_Pa, eta and head_m; rel 1e-9 on power_W.
- **Closed-form 2** (speed_ratio 1.1):
  - Q_eq = **4.36008627e-4**; H = 1.21·(80 − 40000·Q_eq) = **75.6971825 m**; η = **0.618004313**;
  - ΔP = **444377.85 Pa**, so P_out = **1444377.85 Pa**; shaft = **344.864638 W**.
- **NPSHa:**
  - P_v (PR bubble point at 293.15 K) = 391351.429 Pa.
  - Static 0, friction 0: NPSHa = **103.679744 m**.
  - Static 3.0, friction 0.5: **106.179744 m** (rel 1e-9).
- **NPSHr:** with `npsh_required_m = [2.0, 2.5, 3.0, 3.5, 4.0]` (linear: 2 + 2500·Q_eq), at speed 1:
  - NPSHr = 2 + 2500·4.79609489e-4 = **3.19902372 m**; margin = **100.48072 m**.
- **Cavitation refusal:** with `static_head_m = -110.0`, NPSHa = −6.320256 m < NPSHr, so `PumpCavitationError` (match `NPSHa`). With `npsh_check: report` it returns, with `NPSH_margin_m` ≈ **−9.519280** (rel 1e-6).
- **Identity:** for the closed-form 1 curve, R1's outlets, power and duty equal `Pump().solve(inlets, {"P_out": r1.info["P_out_Pa"], "eta": r1.info["eta"]}, thermo)` exactly (`==` on T, P, enthalpy, power_W). Also, a flat curve (`head_m` all 60.8156204, `efficiency` all 0.639804745) gives P_out 1357016.12 Pa.
- **Refusals:** one test per row of the refusal table, each reaching its own check with `pytest.raises(<Class>, match=...)`. Range example: `speed_ratio = 0.5` gives Q_eq = 9.59e-4 > 8.0e-4, which is outside the curve.
- **V1 candidates:**
  - No open worked example is known to the spec author that prints a full pump curve plus a fluid state plus the resulting P_out or NPSHa.
  - **V1 gap. Search:**
    - Perry's 9th ed. §10 (pumps: worked NPSH examples);
    - Karassik et al., *Pump Handbook* 4th ed., ch. 2 (affinity worked examples);
    - Hydraulic Institute ANSI/HI 9.6.1 (citation only);
    - Couper et al., *Chemical Process Equipment* 3rd ed., ch. 7 examples.
  - Only printed inputs and printed results qualify.

## Steps (each at most about 40 minutes, each ending in a push)
1. Create `pump_r1.py`:
   - the error classes, params parsing and validation, PCHIP curve evaluation with the affinity laws, and delegation to R0;
   - info keys without NPSH.
   Add the identity test, closed-form 1 and 2, and the curve and param refusal tests. Push, then open the PR.
2. Add the NPSHa/NPSHr check (eqs. 6–8, `npsh_check`), with the NPSHa, NPSHr and cavitation tests (refuse plus report). Push.
3. Add the catalogue `levels.R1` entry (YAML above) and the V1 case, or record the gap in the row `notes`. Regenerate the docs (`validate_units.py`, then `--audit` separately) and run the gates. Push.

## Review checklist (for the orchestrator)
- R1 delegates the thermodynamics to `Pump().solve` (no copied flash code), and the identity test uses `==`.
- The affinity exponents: Q ∝ s, H ∝ s², η unchanged, NPSHr ∝ s².
- PCHIP has `extrapolate=False`, and an explicit range refusal comes before evaluation (not a NaN check after).
- g = 9.80665 comes from `G_STD`, not retyped.
- P_v is the mixture bubble-point pressure at suction T (not a pure-component Psat).
- NPSHa goes through `npsh_available` (one owner); there is no re-derived formula.
- Every refusal class is reached by its own test; the two `ValueError` subclasses come from the module.
- No edit to `ngdesign/units/pump.py` or any shared module; only the `pump` row's `levels.R1` changes in YAML.
