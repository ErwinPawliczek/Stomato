# compressor R1: performance map with Schultz polytropic head, surge and stonewall

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit spec.
- **Wave/order:** parallel-safe
- **Branch:** `u-lv/compressor` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/compressor_r1.py` (new)
  - `tests/units/flow/test_compressor_r1.py` (new)
  - `data/validation_units/flow/cases/compressor.yaml` (new; only if a V1 case is found)
  - in `data/unit_models/flow.yaml`: the `levels.R1` entry of row `compressor` (and the row `notes` line for a V1 gap)
- **Read-only imports (verified to exist, with signatures):**
  - `ngdesign.units.compressor.Compressor`: the R0 adapter, `Compressor().solve(inlets, params, thermo) -> UnitResult`, params `P_out` (Pa) and `eta_isentropic`
  - `Thermo.flash_ps(z, P, S, molar_flow) -> StreamState`; `Thermo.flash_ph(z, P, H, molar_flow) -> StreamState`
  - `StreamState.mass_flow` (kg/s, property); `Phase.density` (kg/m³)
  - `scipy.interpolate.PchipInterpolator(x, y, axis=0, extrapolate=None)`; `scipy.optimize.brentq(f, a, b, args=(), xtol=2e-12, rtol=8.88e-16, maxiter=100, full_output=False, disp=True)` (scipy 1.18.1)
- **Current state:** the R0 adapter `ngdesign.units.compressor:Compressor` has ports `inlet` → `outlet`.
  - Params: `P_out` (required) and `eta_isentropic` (default 0.75).
  - It computes h2s = `flash_ps(z, P_out, s1)`, h2 = h1 + (h2s − h1)/η and outlet = `flash_ph`; `power_W` = F·(h2 − h1).
  - info: `T_out_isentropic`, `pressure_ratio`, and `polytropic_head_J_kg` (average-Z approximation).
  - It refuses a liquid inlet (vf < 0.999).

## Method
### Equations
Notation: state 1 is the inlet. State 2 is the actual discharge and state 2s the isentropic discharge, both at P₂. v is the specific volume, 1/ρ (m³/kg), of the single phase. M = ṁ/F is the molar mass in kg/mol. Heads are in J/kg.

1. Actual inlet volumetric flow: Q = ṁ/ρ₁.
2. Fan laws at speed ratio s = N/N_map (Perry's 9th ed. §10, compressor laws; API 617 8th ed. §2.x, informative):
   - Q_eq = Q/s;
   - H(Q) = s²·H_map(Q_eq);
   - η(Q) = η_map(Q_eq).
3. Map interpolation: PCHIP over `flow_m3_s`, with no extrapolation.
4. Surge and stonewall limits: Q_surge = `surge_flow_m3_s` (default `flow_m3_s[0]`) and Q_stonewall = `stonewall_flow_m3_s` (default `flow_m3_s[-1]`), both at map speed and compared with Q_eq.
   - Surge margin: SM = Q_eq/Q_surge − 1.
   - Stonewall margin: StM = 1 − Q_eq/Q_stonewall.
5. **Isentropic basis.** H_is(P₂) = (h(P₂, s₁) − h₁)/M. The operating point solves H_is(P₂) = H. The outlet is then R0 with `{"P_out": P₂, "eta_isentropic": η}`.
6. **Polytropic basis** (Schultz, J. Eng. Power 84 (1962) 69–82; ASME PTC 10-1997 §5, the Schultz method):
   - n_s = ln(P₂/P₁) / ln(v₁/v₂s)
   - f = [(h₂s − h₁)/M] / [ (n_s/(n_s − 1))·(P₂·v₂s − P₁·v₁) ] (the Schultz polytropic head factor)
   - Actual work per unit mass: w = H/η_p, so h₂ = h₁ + M·H/η_p and state 2 = `flash_ph(z, P₂, h₂)`.
   - n = ln(P₂/P₁) / ln(v₁/v₂)
   - H_p(P₂) = f·(n/(n − 1))·(P₂·v₂ − P₁·v₁)
   - The operating point solves H_p(P₂) = H.
7. Power: `power_W` = F·(h₂ − h₁) = ṁ·H/η in both bases. A test asserts this identity.

### Algorithm
1. Validate the inlet and params (refusal table). The inlet must be vapour, vf ≥ 0.999, as in R0. The inlet must be single-phase (`len(phases) == 1`).
2. Compute ρ₁, Q and Q_eq.
   - If Q_eq < Q_surge, raise `CompressorSurgeError`.
   - If Q_eq > Q_stonewall, raise `CompressorStonewallError`.
   - Otherwise require Q_eq ∈ [flow_m3_s[0], flow_m3_s[-1]], else raise `CompressorMapRangeError`.
3. Evaluate H and η (eqs. 2–3). Refuse if H ≤ 0 or η ∉ (0, 1].
4. Find P₂ with `brentq(g, a, b, xtol=1e-9*P₁, maxiter=100)`, where g(P₂) = head(P₂) − H:
   - a = P₁·(1 + 1e-6) and b = P₁·`max_pressure_ratio` (default 10);
   - head = H_is (eq. 5) or H_p (eq. 6), according to `efficiency_basis`.
   - If g(b) < 0, raise `CompressorMapRangeError` ("map head exceeds the head at max_pressure_ratio").
   - Each head evaluation flashes 2s (and 2 for the polytropic basis). Every state used must be single-phase; otherwise raise `CompressorTwoPhaseError` with P₂.
   - If brentq raises or hits maxiter, raise `CompressorMapRangeError` with the bracket. Never return an unconverged P₂.
5. Build the outlet:
   - isentropic basis: `r0 = Compressor().solve(inlets, {"P_out": P₂, "eta_isentropic": η}, thermo)`; the outlets and power are r0's;
   - polytropic basis: outlet = `flash_ph(z, P₂, h₁ + M·H/η)`, `power_W` = F·(h₂ − h₁), `duty_W` = 0.
6. Fill info.

### Reduction to the lower level
- With `efficiency_basis: isentropic`, R1's outlets and power equal `Compressor().solve(inlets, {"P_out": info["P_out_Pa"], "eta_isentropic": info["eta"]}, thermo)` exactly (`==`), because R1 delegates.
- A flat map (constant H and η) at speed 1 is R0 at the P_out that makes the isentropic head equal H.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| inlet vf < 0.999, or more than one phase | `CompressorR1SpecError` | `inlet has liquid` |
| `map` missing, or `flow_m3_s` / `head_J_kg` / `efficiency` missing | `CompressorR1SpecError` | `map.<key>` |
| arrays unequal, fewer than 2 points, or flow not strictly increasing | `CompressorR1SpecError` | `strictly increasing` / `same length` |
| `efficiency_basis` not in {polytropic, isentropic} | `CompressorR1SpecError` | `efficiency_basis` |
| `speed_ratio` ≤ 0, or `max_pressure_ratio` ≤ 1 | `CompressorR1SpecError` | the param name |
| surge flow outside the map, or surge ≥ stonewall | `CompressorR1SpecError` | `surge_flow_m3_s` |
| Q_eq < Q_surge | `CompressorSurgeError(CompressorR1SpecError)` | `surge` |
| Q_eq > Q_stonewall | `CompressorStonewallError(CompressorR1SpecError)` | `stonewall` |
| Q_eq outside the map (when the limits are inside it) | `CompressorMapRangeError(CompressorR1SpecError)` | `outside the map` |
| H ≤ 0 or η ∉ (0, 1] | `CompressorR1SpecError` | `head` / `efficiency` |
| no root up to `max_pressure_ratio` | `CompressorMapRangeError` | `max_pressure_ratio` |
| two-phase at a head evaluation | `CompressorTwoPhaseError(CompressorR1SpecError)` | `two-phase` |

All of these are new classes in `compressor_r1.py`.

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `map.flow_m3_s` | number[] | m³/s, actual inlet | required | strictly increasing, ≥ 2 | map flow points at map speed |
| `map.head_J_kg` | number[] | J/kg | required | > 0 | polytropic or isentropic head, matching `efficiency_basis` |
| `map.efficiency` | number[] | – | required | (0, 1] | polytropic or isentropic efficiency |
| `efficiency_basis` | string | – | `"polytropic"` | polytropic / isentropic | basis of the map's head and efficiency |
| `speed_ratio` | number | – | 1.0 | > 0 | N/N_map |
| `surge_flow_m3_s` | number | m³/s | `flow_m3_s[0]` | within the map | surge line at map speed |
| `stonewall_flow_m3_s` | number | m³/s | `flow_m3_s[-1]` | within the map, > surge | choke line at map speed |
| `max_pressure_ratio` | number | – | 10.0 | > 1 | upper bracket for P₂ |

```yaml
    R1:
      status: provisional
      adapter: ngdesign.units.flow.compressor_r1:CompressorR1
      params:
        type: object
        required: [map]
        properties:
          map:
            type: object
            required: [flow_m3_s, head_J_kg, efficiency]
            properties:
              flow_m3_s: {type: array, items: {type: number}, description: 'actual inlet flow points at map speed, m3/s, strictly increasing'}
              head_J_kg: {type: array, items: {type: number}, description: 'head at each point, J/kg (basis per efficiency_basis)'}
              efficiency: {type: array, items: {type: number}, description: 'efficiency at each point, (0, 1]'}
          efficiency_basis: {type: string, enum: [polytropic, isentropic], description: 'default polytropic'}
          speed_ratio: {type: number, description: 'N / N_map (fan laws), default 1.0'}
          surge_flow_m3_s: {type: number, description: 'surge flow at map speed, m3/s, default first map point'}
          stonewall_flow_m3_s: {type: number, description: 'stonewall flow at map speed, m3/s, default last map point'}
          max_pressure_ratio: {type: number, description: 'upper bracket for the discharge pressure solve, default 10'}
      note: performance map (head/efficiency vs flow, fan laws, surge/stonewall), Schultz polytropic
      validation: []
      end_state: true
```

## Outputs
- Port `outlet`: a PH flash at P₂ (via R0 for the isentropic basis).
- `duty_W = 0`; `power_W` = F·(h₂ − h₁) > 0.
- info:
  - `P_out_Pa`, `pressure_ratio`, `Q_actual_m3_s`, `Q_equiv_m3_s`;
  - `head_J_kg` (the operating head), `eta` (on the map's basis), `speed_ratio`;
  - `surge_margin` and `stonewall_margin` (dimensionless);
  - for the polytropic basis also `schultz_f`, `n_polytropic` and `n_isentropic_path`;
  - `T_out_K`.

## Tests
Inlet for every test: the R0 example feed, `Compressor.example_case()` (dry gas, 322.15 K, 3.447 MPa, 691.706196 mol/s), flashed with `pr`. Independent script: `scratchpad/unit-specs/calc_compressor.py` (direct PR flashes plus a 200-step bisection; no brentq and no R1 code).
- Measured inlet: M = 0.0201670784 kg/mol, ρ₁ = 28.380163 kg/m³, Q = **0.491529703 m³/s**.
- **Map** (linear data):
  - `flow_m3_s = [0.30, 0.40, 0.50, 0.60, 0.70]`
  - `head_J_kg = [72000, 66000, 60000, 54000, 48000]`
  - `efficiency = [0.69, 0.72, 0.75, 0.78, 0.81]`
  - At Q: H = **60508.2178 J/kg**, η = **0.747458911**, surge_margin = **0.638432344**, stonewall_margin = **0.29781471**.
- **Closed-form, isentropic basis:**
  - P_out = **5540987.99 Pa** (ratio 1.60748128), T_out = **364.548325 K**, power_W = **1129254.14 W**.
  - Tolerances: P_out rel 1e-7, T rel 1e-7, power rel 1e-7.
- **Closed-form, polytropic basis:**
  - P_out = **5499757.94 Pa** (ratio 1.59552014), T_out = **364.402793 K**;
  - schultz_f = **0.999768572**, n_polytropic = **1.37543075**, n_isentropic_path = **1.25477227**;
  - power_W = **1129254.14 W**, which equals ṁ·H/η = 13.9497…·60508.2178/0.747458911 in both bases.
  - Tolerances: rel 1e-7 (f and n rel 1e-6).
- **Speed 1.05, polytropic:** Q_eq = **0.468123527**, H = **68258.6287 J/kg**, η = **0.740437058**, P_out = **5813393.74 Pa** (rel 1e-7).
- **Self-consistency:** for the polytropic case, recompute H_p from the returned outlet state with eq. 6 inside the test; it equals H to rel 1e-8.
- **Identity:** isentropic basis gives `==` against `Compressor().solve(inlets, {"P_out": info["P_out_Pa"], "eta_isentropic": info["eta"]}, thermo)` on outlet T, P, enthalpy and power_W.
- **Refusals:** one test per table row.
  - `speed_ratio = 1.8` gives Q_eq = 0.273 < 0.30, so surge.
  - `speed_ratio = 0.6` gives Q_eq = 0.819 > 0.70, so stonewall.
  - `max_pressure_ratio = 1.2` gives no root.
  - Each test uses `pytest.raises(<Class>, match=...)`.
- **V1 candidates:**
  - ASME PTC 10-1997 contains sample calculations of the Schultz polytropic head (citation; verify that an appendix example prints inputs and results).
  - Schultz 1962 prints a worked comparison.
  - The spec author has not seen their numbers, so this is a **V1 gap. Search:**
    - ASME PTC 10-1997 appendices;
    - Schultz, J. Eng. Power 84 (1962);
    - Ludwig, *Applied Process Design* vol. 3, 4th ed., ch. 15 (polytropic examples);
    - Perry's 9th ed. §10 compressor examples.
  - Only printed inputs and results qualify, and only on a property basis the harness can reproduce (otherwise record it as `assessed`).

## Steps (each at most about 40 minutes, each ending in a push)
1. Create `compressor_r1.py`:
   - the errors, params parsing, map PCHIP plus fan laws, surge/stonewall/range checks;
   - the isentropic basis (brentq on H_is, delegation to R0).
   Add the map, isentropic closed-form and identity tests, plus the param/range/surge/stonewall refusals. Push, then open the PR.
2. Add the polytropic basis (eq. 6 head function, outlet construction, Schultz info keys), with the polytropic closed-form, speed 1.05, self-consistency, two-phase and no-root refusal tests. Push.
3. Add the catalogue `levels.R1` (YAML above), the V1 case or the recorded gap, the docs regeneration and the gates. Push.

## Review checklist (for the orchestrator)
- Schultz f, n and H_p exactly as in eq. 6. Specific volumes are per kg (1/ρ), and heads are per kg (divided by M = ṁ/F).
- For the polytropic basis, the actual work is H/η_p, and P₂ is solved so that the head computed from the actual end state equals the map head (not the isentropic shortcut).
- brentq has explicit xtol, maxiter and a sign check at b, and each failure maps to a typed refusal. No unconverged return.
- The surge and stonewall checks compare Q_eq, the flow at map speed, with the map-speed limits.
- The isentropic basis delegates to `Compressor().solve`, with an `==` identity test.
- Every state used in a head evaluation is single-phase, else a typed refusal.
- No edits to `units/compressor.py`; only the `compressor` row's `levels.R1` changes in YAML.
