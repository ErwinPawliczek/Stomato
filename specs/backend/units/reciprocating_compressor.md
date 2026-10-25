# reciprocating_compressor R1: cylinder capacity vs clearance, and gas rod load

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit spec.
- **Wave/order:** parallel-safe
- **Branch:** `u-lv/reciprocating_compressor` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/reciprocating_compressor_r1.py` (new)
  - `tests/units/flow/test_reciprocating_compressor_r1.py` (new)
  - `data/validation_units/flow/cases/reciprocating_compressor.yaml` (new; only if a V1 case is found)
  - in `data/unit_models/flow.yaml`: the `levels.R1` entry of row `reciprocating_compressor` (and the row `notes` line for a V1 gap)
- **Read-only imports (verified to exist, with signatures):**
  - `ngdesign.units.flow.reciprocating_compressor.ReciprocatingCompressor`: the R0 adapter, `solve(inlets, params, thermo) -> UnitResult`
  - `ngdesign.units.flow.reciprocating_compressor._k_ideal(state: StreamState, thermo: Thermo, what: str) -> float`: k = Cp/(Cp − R) on the vapour phase
  - `ngdesign.units.flow.reciprocating_compressor.ReciprocatingCompressorSpecError` (`ValueError`)
  - `ngdesign.units._physics.efficiency.isentropic_step(state, P_out, eta, thermo, mode="compress") -> tuple[StreamState, float]`
  - `Thermo.flash_pt(z, T, P, molar_flow) -> StreamState`
  - `Phase.z_factor` (float or None) and `Phase.density`
- **Current state:** the R0 adapter `ngdesign.units.flow.reciprocating_compressor:ReciprocatingCompressor` has ports `inlet` → `outlet`.
  - Params: `P_out` (required), `n_stages` (default 1), `eta_isentropic` (0.75), `T_intercool` (optional), `clearance` (0.10) and `loss_allowance` (0.0).
  - Equal stage ratios r = (P_out/P_in)^(1/n). Each stage is one `isentropic_step`, followed by intercooling to `T_intercool` (by `flash_pt`) when that is below the stage discharge T and it is not the last stage. `duty_W` = the intercooler duty.
  - info: `pressure_ratio_per_stage`, `k_suction_ideal`, `volumetric_efficiency` (stage 1, E_v = 1 − L − C·(r^(1/k) − 1)), `Q_suction_m3_s` and `displacement_m3_s`.

## Method
### Equations
For each stage i, with suction pressure P_s,i = P_in·r^(i−1) and discharge P_d,i = P_in·r^i:
1. Stage suction state S_i:
   - S_1 is the inlet.
   - S_{i+1} = `flash_pt(z, T_intercool, P_d,i, F)` if `T_intercool` is set and T_intercool < T(D_i); otherwise S_{i+1} = D_i.
   - The stage discharge is D_i = `isentropic_step(S_i, P_d,i, η, thermo, "compress")[0]`.
   - This is exactly R0's sequence.
2. Required suction volumetric flow: Q_s,i = ṁ/ρ(S_i).
3. Piston and rod areas: A_p = π·D_b²/4 and A_r = π·d_r²/4.
4. Displacement per cylinder (GPSA Engineering Data Book, 13th ed., Section 13, piston displacement; API 618 5th ed., definitions):
   - double-acting: PD = (2·A_p − A_r)·S·N/60;
   - single-acting head end: PD = A_p·S·N/60.
5. Volumetric efficiency with the compressibility correction (GPSA Section 13, the VE equation; Bloch & Hoefner, *Reciprocating Compressors* (1996), ch. 2):
   - E_v,i = 1 − L − C_i·((Z_s/Z_d)·r^(1/k_i) − 1)
   - k_i = `_k_ideal(S_i, ...)`; Z_s = Z(S_i) and Z_d = Z(D_i), each the single-phase `z_factor`.
   - With `z_ratio_correction = false`, use Z_s/Z_d = 1. That is R0's formula.
6. Stage capacity: Cap_i = n_cyl,i·PD_i·E_v,i (m³/s at suction). Capacity ratio: Cap_i/Q_s,i.
7. Clearance pocket needed to match the flow (capacity control by added clearance):
   - C_req,i = (1 − L − Q_s,i/(n_cyl,i·PD_i)) / ((Z_s/Z_d)·r^(1/k_i) − 1).
   - This is closed form, because E_v is linear in C.
8. Gas rod load, crankcase at P_cc (GPSA Section 13, rod load; API 618 §6.6, "combined rod load" with gas load only at R1). With F(P_HE, P_CE) = P_HE·A_p − P_CE·(A_p − A_r) − P_cc·A_r:
   - double-acting: compression load F_c = F(P_d, P_s); tension load F_t = −F(P_s, P_d);
   - single-acting head end: F_c = F(P_d, P_cc); F_t = −F(P_s, P_cc).
   - Gas-load reversal: both F_c > 0 and F_t > 0.
   - Inertia loads are out of scope at R1; say so in the docstring.

### Algorithm
1. Validate the params (R0 keys plus the R1 keys). `len(cylinders)` must equal `n_stages`.
2. Run `r0 = ReciprocatingCompressor().solve(inlets, r0_params, thermo)`, where r0_params = the R0 keys, with `clearance` = `cylinders[0].clearance`.
3. Re-traverse the stages with eq. 1, collecting S_i and D_i.
   - Then assert the final state equals r0's outlet (`==` on T, P and enthalpy); a mismatch raises `RuntimeError`, which is a bug, not a refusal.
   - The re-run is deterministic; it exists to expose the stage states without editing R0.
4. Per stage, compute eqs. 2–8.
   - If Cap_i < Q_s,i, raise `RecipCapacityError`, naming the stage, Cap and Q.
   - If `rod_load_limit_N` is given and F_c > its compression limit or F_t > its tension limit, raise `RecipRodLoadError`, naming the stage and the direction.
   - With `capacity_control: "clearance_pocket"`, also compute C_req,i. If C_req,i < C_i, raise `RecipCapacityError`; this cannot occur when Cap ≥ Q, so it is a guard (document it). If C_req,i ≥ 1, report it as a refusal too.
5. Return r0's outlets, duty and power, with info = r0.info plus the per-stage keys.

There is no iteration.

### Reduction to the lower level
- R1's outlets, `power_W` and `duty_W` equal R0's exactly (`==`) for any geometry.
- With `z_ratio_correction: false`, `volumetric_efficiency_stage1` equals R0's `info["volumetric_efficiency"]` exactly (`==`): the same formula, k and clearance.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| any R0 refusal | R0's `ReciprocatingCompressorSpecError` (propagated) | R0 messages |
| `cylinders` missing or of length ≠ `n_stages` | `RecipR1SpecError` | `cylinders` |
| a cylinder has bore, stroke or `n_cylinders` ≤ 0, rod ≤ 0 or ≥ bore, action not in {double, single_head_end}, or clearance ∉ [0, 1) | `RecipR1SpecError` | the field name, with the stage index |
| `speed_rpm` ≤ 0 | `RecipR1SpecError` | `speed_rpm` |
| `capacity_control` not in {none, clearance_pocket} | `RecipR1SpecError` | `capacity_control` |
| E_v,i ≤ 0 | `RecipCapacityError(RecipR1SpecError)` | `volumetric efficiency` |
| Cap_i < Q_s,i | `RecipCapacityError` | `capacity` |
| C_req,i ≥ 1 | `RecipCapacityError` | `clearance` |
| rod load above its limit | `RecipRodLoadError(RecipR1SpecError)` | `rod load` |
| Z missing (`z_factor` None) with the correction on | `RecipR1SpecError` | `z_factor` |

## Params
The R0 keys are unchanged: `P_out`, `n_stages`, `eta_isentropic`, `T_intercool`, `loss_allowance`. R0's `clearance` is replaced by the per-stage `cylinders[].clearance`; refuse `clearance` at R1 with `RecipR1SpecError("use cylinders[].clearance")`.

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `cylinders[i].n_cylinders` | integer | – | 1 | ≥ 1 | parallel cylinders on stage i |
| `cylinders[i].bore_m` | number | m | required | > 0 | cylinder bore |
| `cylinders[i].stroke_m` | number | m | required | > 0 | stroke |
| `cylinders[i].rod_diameter_m` | number | m | required | 0 < d < bore | piston rod diameter |
| `cylinders[i].action` | string | – | `"double"` | double / single_head_end | acting |
| `cylinders[i].clearance` | number | – | 0.10 | [0, 1) | fixed clearance fraction |
| `speed_rpm` | number | rpm | required | > 0 | crank speed |
| `z_ratio_correction` | boolean | – | true | – | use Z_s/Z_d in E_v |
| `capacity_control` | string | – | `"none"` | none / clearance_pocket | report the required clearance pocket |
| `P_crankcase_Pa` | number | Pa | 101325 | > 0 | crankcase or distance-piece pressure |
| `rod_load_limit_N.compression` / `.tension` | number | N | optional | > 0 | allowable gas rod loads |

```yaml
    R1:
      status: provisional
      adapter: ngdesign.units.flow.reciprocating_compressor_r1:ReciprocatingCompressorR1
      params:
        type: object
        required: [P_out, cylinders, speed_rpm]
        properties:
          P_out: {type: number, description: 'outlet pressure, Pa'}
          n_stages: {type: integer, description: 'stages, default 1'}
          eta_isentropic: {type: number, description: 'stage isentropic efficiency, default 0.75'}
          T_intercool: {type: number, description: 'intercooler outlet temperature, K (optional)'}
          loss_allowance: {type: number, description: 'valve-loss allowance L in E_v, default 0'}
          cylinders:
            type: array
            description: 'one entry per stage'
            items:
              type: object
              required: [bore_m, stroke_m, rod_diameter_m]
              properties:
                n_cylinders: {type: integer, description: 'parallel cylinders, default 1'}
                bore_m: {type: number, description: 'bore, m'}
                stroke_m: {type: number, description: 'stroke, m'}
                rod_diameter_m: {type: number, description: 'rod diameter, m'}
                action: {type: string, enum: [double, single_head_end], description: 'default double'}
                clearance: {type: number, description: 'clearance fraction, default 0.10'}
          speed_rpm: {type: number, description: 'crank speed, rpm'}
          z_ratio_correction: {type: boolean, description: 'Zs/Zd in volumetric efficiency, default true'}
          capacity_control: {type: string, enum: [none, clearance_pocket], description: 'default none'}
          P_crankcase_Pa: {type: number, description: 'crankcase pressure, Pa, default 101325'}
          rod_load_limit_N:
            type: object
            properties:
              compression: {type: number, description: 'allowable gas rod load in compression, N'}
              tension: {type: number, description: 'allowable gas rod load in tension, N'}
      note: per-stage cylinder capacity vs clearance (GPSA VE with Zs/Zd), clearance pocket, gas rod load
      validation: []
      end_state: true
```

## Outputs
- Port `outlet`, `duty_W` and `power_W`: R0's.
- info: R0 keys, plus per stage i (1-based):
  - `displacement_stage{i}_m3_s` (n_cyl·PD), `volumetric_efficiency_stage{i}`, `capacity_stage{i}_m3_s`, `Q_suction_stage{i}_m3_s`, `capacity_ratio_stage{i}`;
  - `rod_load_compression_stage{i}_N`, `rod_load_tension_stage{i}_N`, `rod_reversal_stage{i}` (1.0 or 0.0);
  - with `clearance_pocket`: `clearance_required_stage{i}`.

## Tests
Base: the R0 `example_case` (2 stages, 3.447 → 8.0 MPa, η 0.75, T_intercool 322.15 K, loss 0.02, flashed with `pr`). The R1 additions:
- `speed_rpm` 900;
- stage 1: one double-acting cylinder, bore 0.34, stroke 0.20, rod 0.06, clearance 0.10;
- stage 2: one double-acting cylinder, bore 0.28, stroke 0.20, rod 0.06, clearance 0.10.

Independent script: `scratchpad/unit-specs/calc_reciprocating_compressor.py`. Tolerance rel 1e-9 on geometric quantities and rel 1e-7 on anything using thermo.

| quantity | stage 1 | stage 2 |
|---|---|---|
| P_s / P_d (Pa) | 3447000 / 5251285.56 | 5251285.56 / 8000000 |
| k (ideal) | 1.21611463 | 1.20058113 |
| Z_s / Z_d | 0.914486006 / 0.917247872 | 0.874642142 / 0.885541882 |
| Q_s (m³/s) | 0.491529703 | 0.308587799 |
| A_p (m²) | 0.0907920277 | 0.061575216 |
| A_r (m²) | 0.00282743339 | 0.00282743339 |
| PD per cylinder (m³/s) | **0.536269866** | **0.360968996** |
| E_v (Z-corrected) | **0.939062958** | **0.939750548** |
| E_v (no Z) | 0.93863731 | 0.938002767 |
| capacity (m³/s) | **0.503591167** | **0.339220812** |
| C_req (clearance pocket) | **0.154941454** | **0.310843318** |
| rod load compression (N) | **173274.417** | **183813.856** |
| rod load tension (N) | **149253.574** | **146919.708** |

- **Identity tests:**
  - outlets, power and duty `==` R0;
  - with `z_ratio_correction: false`, `volumetric_efficiency_stage1 == r0.info["volumetric_efficiency"]` (0.93863731).
- **Refusals:**
  - stage-1 bore 0.30 gives capacity 0.3903 < 0.4915, so `RecipCapacityError` (match `capacity`);
  - `rod_load_limit_N.compression = 150000` gives stage 1 at 173274 N, so `RecipRodLoadError` (match `rod load`);
  - a length mismatch (one cylinder for 2 stages);
  - rod ≥ bore;
  - a bad action;
  - the `clearance` key at R1;
  - each with `pytest.raises(<Class>, match=...)`.
- **V1 candidates:**
  - GPSA Engineering Data Book Section 13 includes worked reciprocating-compressor examples (capacity, VE, rod load). It is citation only, and the spec author has not verified the printed numbers, so this is a **V1 gap.**
  - **Search:**
    - GPSA 13th ed. Section 13 examples;
    - Bloch & Hoefner 1996 ch. 2–3;
    - Ludwig, *Applied Process Design* vol. 3, 4th ed., ch. 15 reciprocating examples;
    - Perry's 9th ed. §10.
  - Only printed inputs and results qualify; VE and rod-load examples with printed pressures and geometry can be fed as params with a defined gas.

## Steps (each at most about 40 minutes, each ending in a push)
1. Create `reciprocating_compressor_r1.py`:
   - the errors, params validation, delegation to R0, and the stage re-traversal with its `==` consistency assertion;
   - PD, E_v (both modes), capacity and the capacity refusal.
   Add the identity tests, the stage-table tests (PD, E_v, capacity) and the geometry refusals. Push, then open the PR.
2. Add the clearance pocket (eq. 7) and rod loads (eq. 8) with reversal and limits, with the C_req, rod-load and rod-limit refusal tests. Push.
3. Add the catalogue `levels.R1` (YAML above), the V1 case or the recorded gap, the docs regeneration and the gates. Push.

## Review checklist (for the orchestrator)
- The stage states come from the same call sequence as R0, and the final-state `==` assertion exists.
- PD: double-acting uses 2·A_p − A_r; single uses A_p; ·S·N/60.
- E_v: (Z_s/Z_d)·r^(1/k), with Z_d from the actual stage discharge state; the no-Z mode matches R0 exactly.
- C_req is closed form, as in eq. 7.
- Rod load F(P_HE, P_CE) = P_HE·A_p − P_CE·(A_p − A_r) − P_cc·A_r, with the stated sign conventions. The docstring says inertia is out of scope.
- No edits to the R0 module; only the `reciprocating_compressor` row's `levels.R1` changes in YAML.
