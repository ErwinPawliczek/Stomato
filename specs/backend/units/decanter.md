# decanter R1: Stokes settling with Richardson-Zaki hindered settling (ideal-settler entrainment)

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/decanter` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/decanter_r1.py` (new): `DecanterR1`, `DecanterR1SpecError`, and the pure functions below
  - `tests/units/separation/test_decanter_r1.py` (new)
  - `data/validation_units/separation/cases/decanter.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `decanter`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separation.decanter.Decanter` (R0) and `DecanterSpecError`; do not edit `decanter.py`
  - `ngdesign.contracts` (`PhaseKind`, `StreamState`, `UnitResult`); `Thermo`
- **Current state:**
  - R0 runs a PT flash at `(T_in, P_in − dP)` and requires exactly two liquids and no vapour (typed refusal otherwise).
  - The light phase (by density) goes to `light_out`, the heavy one to `heavy_out`. Each outlet comes from `phase_outlet`, a per-phase `flash_pt`.
  - `duty_W` is the closure.
  - A test check on `pr` gives H2O/nC5 at 278.15 K and 1 bar: hc_liquid ρ = 659.9 kg/m³, μ = 2.24e-4 Pa·s; aqueous ρ = 859.4 kg/m³, μ = 1.52e-3 Pa·s. Both viscosities are present.

## Method
### Equations (SI)
Sources: Sinnott, *Coulson & Richardson's Chemical Engineering* Vol. 6, §10.6.3 "Decanters"; Richardson & Zaki, Trans. IChemE 32:35 (1954); Hazen (1904), ideal settler.
- **D1 Stokes terminal velocity** of a dispersed droplet in the continuous phase: `u_t = g·d²·|ρ_d − ρ_c|/(18·μ_c)`, g = 9.80665. Validity: `Re_t = ρ_c·u_t·d/μ_c < 1`. Outside that range the unit refuses (R1 is a Stokes model).
- **D2 Dispersed volume fraction** in the settling zone: `φ = Q_d/(Q_c + Q_d)`, using the volumetric flows of the two R0 outlet phases.
- **D3 Richardson-Zaki exponent** (no wall correction):
  | Re_t | n |
  |---|---|
  | < 0.2 | 4.65 |
  | 0.2 to < 1 | 4.4·Re_t^−0.03 |
  | 1 to < 500 | 4.4·Re_t^−0.1 (not reached under D1's validity) |
  | ≥ 500 | 2.4 |
- **D4 Hindered velocity:** `u_h = u_t·(1 − φ)^n`.
- **D5 Ideal-settler separation efficiency** (Hazen), for droplets of size d entering uniformly: `η = min(1, u_h·A_i/Q_c)`.
  - `A_i` is the interface area.
  - For a horizontal cylinder with the interface at the centre line, `A_i = D·L` (Sinnott §10.6.3).
- **D6 Entrainment:** the fraction `1 − η` of the dispersed phase leaves with the continuous phase.

### Algorithm
1. `r0 = Decanter().solve(inlets, {"dP": params.get("dP", 0.0)}, thermo)`. Its outlets each carry one liquid phase.
2. The dispersed phase is the outlet named by `dispersed_phase` (`"light"` or `"heavy"`, required); the other is continuous.
   - Densities and viscosities come from each outlet's single phase.
   - `μ_c` falls back to `continuous_viscosity_Pa_s` if the phase viscosity is None; otherwise refuse.
   - Volumetric flows: `Q = mass_flow/ρ`.
3. `A_i`: the `interface_area_m2` param, or `diameter_m·length_m`. Exactly one of the two forms; refuse both or neither.
4. Compute D1–D5. If `Re_t ≥ 1`, refuse.
5. If `η == 1`, the outlets are R0's exactly.
   Otherwise:
   - the dispersed outlet is R0's dispersed outlet `model_copy(update={"molar_flow": η·n_d})`;
   - the continuous outlet is `thermo.flash_pt(z_mix, T, P, n_c + (1−η)·n_d)`, with `z_mix` the flow-weighted mix of the continuous outlet and the entrained dispersed liquid. Two coexisting equilibrium liquids at the same T and P, so the flash returns the same tie line.
6. `duty_W` is the closure recomputed from the R1 outlets. `power_W = 0`.

### Reduction to the lower level
When `u_h·A_i ≥ Q_c` (η = 1), every outlet equals R0's exactly, with the same duty. This is the identity test, with a large area.

### Refusals (`DecanterR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `dispersed_phase` not in {light, heavy} | `dispersed_phase` |
| both or neither of `interface_area_m2` and (`diameter_m`, `length_m`) | `interface_area_m2` |
| any geometry value ≤ 0 | the parameter name |
| `droplet_diameter_m` ≤ 0 or missing | `droplet_diameter_m` |
| continuous viscosity unavailable | `continuous_viscosity_Pa_s` |
| `Re_t ≥ 1` (outside Stokes) | `Stokes` |

R0's `DecanterSpecError` (single liquid or vapour present) propagates unchanged.

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| dP | number | Pa | 0 | ≥ 0 | R0 pressure drop |
| dispersed_phase | string | – | required | light \| heavy | which outlet phase forms the droplets |
| droplet_diameter_m | number | m | required | > 0 | design droplet size |
| interface_area_m2 | number | m² | one form required | > 0 | settling interface area |
| diameter_m, length_m | number | m | one form required | > 0 | horizontal vessel with a centre-line interface |
| continuous_viscosity_Pa_s | number | Pa·s | phase value | > 0 | override |

```yaml
type: object
required: [dispersed_phase, droplet_diameter_m]
properties:
  dP: {type: number, minimum: 0, description: 'pressure drop, Pa; default 0'}
  dispersed_phase: {type: string, enum: [light, heavy], description: 'phase forming the droplets'}
  droplet_diameter_m: {type: number, exclusiveMinimum: 0, description: 'design droplet diameter, m'}
  interface_area_m2: {type: number, exclusiveMinimum: 0, description: 'interface (settling) area, m2'}
  diameter_m: {type: number, exclusiveMinimum: 0, description: 'horizontal vessel diameter, m (interface at the centre line)'}
  length_m: {type: number, exclusiveMinimum: 0, description: 'horizontal vessel length, m'}
  continuous_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'continuous-phase viscosity override, Pa s'}
```

## Outputs
- **Ports:** `light_out` and `heavy_out` (step 5).
- **`info`:** `u_t_m_s`, `Re_t`, `phi_dispersed`, `rz_exponent`, `u_h_m_s`, `interface_area_m2`, `overflow_rate_m_s` (= Q_c/A_i), `separation_efficiency` (η), `entrained_dispersed_fraction` (1 − η).

## Tests
Numbers come from `scratchpad/unit-specs/calc_decanter.py` (math only).
- **CF1**, through the pure function `stokes_velocity(d, rho_d, rho_c, mu_c)` with d = 150e-6, ρ_d = 900, ρ_c = 1000, μ_c = 1.0e-3:
  - `u_t = 1.22583125e-3 m/s`, `Re_t = 0.183874687`;
  - rtol 1e-9.
- **CF2**, through `rz_exponent(Re)` and `hindered_velocity(u_t, phi, n)` with Q_c = 1.5e-3 and Q_d = 0.3e-3:
  - `φ = 0.166666667`, `n = 4.65`, `u_h = 5.25095014e-4`;
  - rtol 1e-9.
- **CF3**, through `settler_efficiency(u_h, A_i, Q_c)`:
  - A_i = 0.5 → `η = 0.175031671`;
  - A_i = 2.0 → `η = 0.700126685`;
  - rtol 1e-9.
- **CF4 geometry:** D = 0.8, L = 2.5 → `A_i = 2.0`, exact.
- **CF5 exponent branches:** `rz_exponent(0.1) = 4.65`; `rz_exponent(0.5) = 4.4·0.5^−0.03`; `rz_exponent(600) = 2.4`. Exact.
- **Identity:** the R0 example feed (H2O/nC5 at 278.15 K, 1 bar) with `dispersed_phase="light"`, d = 150e-6 and `interface_area_m2 = 1e4` gives η = 1, outlets `==` R0's.
- **Unit-level entrainment:** the same feed with `interface_area_m2` chosen so that 0 < η < 1:
  - assert `heavy_out` contains the entrained light liquid, i.e. its nC5 mole flow is greater than R0's;
  - assert `light_out.molar_flow == η·R0 light flow` to 1e-12 relative;
  - balances: moles at 1e-12, energy at 1e-8.
- **Refusals:** one test per row. For the Stokes refusal, use a droplet of 2e-3 m.
- **V1 candidates:**
  - Sinnott, *Coulson & Richardson's Chemical Engineering* Vol. 6, 4th ed., §10.6.3, Example 10.3: a decanter design separating light oil from water, which prints the flows, densities, viscosities, droplet size, droplet velocity and interface area. Transcribe the printed droplet velocity and interface area as expected values; the unit's `info.u_t_m_s` is the comparable quantity. Note that the package's densities differ from the book's, so the case passes the book's ρ and μ through the overrides only if params allow it. They don't for ρ: record any density-driven miss in `assessed`.
  - If no accessible copy can be verified: V1 gap. Search Sinnott Example 10.3, and Perry's 8th ed. Sect. 15 (decanter examples).

## Steps
1. Pure functions plus CF1–CF5, the module skeleton and the error class. Push, then open the PR.
2. The `DecanterR1` adapter, with the identity, entrainment and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.decanter_r1:DecanterR1`). Regenerate the docs, then `--audit`. Push.
3. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- Stokes validity is enforced, never extrapolated.
- R-Z branches exactly as in D3.
- η is capped at 1.
- The dispersed outlet is scaled, not re-flashed; the continuous outlet is re-flashed as a two-liquid mix only.
- The η = 1 path returns R0's objects unchanged.
