# hydrocyclone R1: Lapple cut size and grade efficiency, Shepherd-Lapple pressure drop

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/hydrocyclone` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/hydrocyclone_r1.py` (new): `HydrocycloneR1`, `HydrocycloneR1SpecError`, and the pure functions below
  - `tests/units/separation/test_hydrocyclone_r1.py` (new)
  - `data/validation_units/separation/cases/hydrocyclone.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `hydrocyclone`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separation.hydrocyclone.Hydrocyclone` (R0) and `HydrocycloneSpecError`
  - `numpy.polynomial.legendre.leggauss(deg)`
  - `ngdesign.contracts`; `Thermo`
- **Current state:**
  - R0 takes per-component `underflow_fractions` (the spec) and `dP` on the overflow, and uses `split_by_component`.
  - The R0 example is deoiling produced water (H2O/nC5), with 95 % of the water to the underflow.

## Method
The row names "Lapple / Barth cut size". R1 implements **Lapple**, the standard textbook cyclone model, for both gas cyclones and liquid hydrocyclones: the same residence-time derivation with the fluid's viscosity and the density difference. Barth's static-particle model is not part of R1. Record that in the catalogue note.

### Equations (SI)
Sources: Lapple, C. E. (1951), in *Fluid and Particle Mechanics*; Shepherd & Lapple, Ind. Eng. Chem. 31:972 (1939) and 32:1246 (1940). Both are reproduced in Cooper & Alley, *Air Pollution Control: A Design Approach*, Ch. 4, and in Perry's 8th ed. Sect. 17 (gas-solid separations). Record the exact equation numbers from the copy used.
- **H1 Inlet velocity:** `v_i = Q/(W·H)`, with W the inlet width, H the inlet height and Q the actual volumetric flow of the fluid.
- **H2 Effective turns:** `N_e = (L_b + L_c/2)/H`, or the given `N_e`.
- **H3 Lapple cut diameter:** `d50 = sqrt(9·μ·W/(2π·N_e·v_i·|ρ_p − ρ_f|))`.
- **H4 Grade efficiency:** `η(d) = 1/(1 + (d50/d)²)`.
- **H5 Overall efficiency** for a Rosin-Rammler mass distribution `F(d) = 1 − exp(−(d/d_RR)^n)`:
  - `E = ∫_0^1 η(d(F)) dF`, with `d(F) = d_RR·(−ln(1−F))^(1/n)`;
  - evaluated by **64-point Gauss-Legendre** on F ∈ [0, 1] (`leggauss(64)`, F = (x+1)/2, weights w/2).
  - A monodisperse `particle_diameter_m` gives `E = η(d)`.
- **H6 Shepherd-Lapple pressure drop:** `ΔP = ½·ρ_f·v_i²·N_H`, with `N_H = K·H·W/D_e²`.
  - K = 16 for a tangential inlet, the R1 default; `K_inlet` overrides it.
  - D_e is the vortex-finder (gas outlet) diameter.
- **H7 Split:** particles heavier than the fluid report to the underflow.
  - The particle components' underflow fraction is `E + (1 − E)·R_f`.
  - Every fluid component's underflow fraction is `R_f` (`fluid_underflow_fraction`, the flow-split ratio; default 0).
  - If `ρ_p < ρ_f` (light droplets, for example oil in water), the separated fraction reports to the **overflow**: particle overflow fraction `E + (1 − E)·(1 − R_f)`, i.e. particle underflow fraction `(1 − E)·R_f`.

### Algorithm
1. Validate the params (refusal table).
2. Fluid properties come from `inlets["inlet"]`.
   - The continuous fluid is the inlet phase with the **largest volume fraction** (`mole_fraction·MW/ρ`) **among phases that contain no particle component above 0.5 mole fraction**.
   - `ρ_f` and `μ_f` are that phase's values; the `fluid_viscosity_Pa_s` param overrides a None viscosity.
   - `Q` is the inlet's total mass flow over `ρ_f`. This is the slurry approximation; record it in the module docstring.
3. `ρ_p` comes from `particle_density_kg_m3` and is **required**. The package treats solids such as SiO2 as a PR liquid (1451 kg/m³ against about 2650 real), so particle density is never taken from a phase.
4. Compute H1–H5, then H7, to get `underflow_fractions` for every feed component.
5. `dP`: the `dP` param if given; otherwise H6 (needs `outlet_diameter_m`, or refuse).
6. Delegate the material split to R0: `Hydrocyclone().solve(inlets, {"underflow_fractions": fractions, "dP": dP}, thermo)`. Return its outlets and duty with R1's `info` added.

### Reduction to the lower level
R1 is R0 with computed fractions. The identity test calls R0 with `info`'s fractions, reported back as `info.underflow_fraction_<cid>`, and the `info.dP_Pa`; the outlets must be `==` R1's.

### Refusals (`HydrocycloneR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `particle_components` empty or naming a component not in the feed | `particle_components` |
| `particle_density_kg_m3` ≤ 0 or missing | `particle_density_kg_m3` |
| `particle_density_kg_m3 == ρ_f` | `density difference` |
| any geometry value ≤ 0, missing W or H, missing both (`body_length_m`, `cone_length_m`) and `N_e` | the parameter name |
| neither `particle_diameter_m` nor (`d_rr_m`, `n_rr`); or both | `particle_diameter_m` |
| `fluid_underflow_fraction` outside [0, 1) | `fluid_underflow_fraction` |
| no `dP` and no `outlet_diameter_m` | `outlet_diameter_m` |
| fluid viscosity unavailable | `fluid_viscosity_Pa_s` |

## Params
| name | type | unit | required/default | meaning |
|---|---|---|---|---|
| particle_components | array of string | – | required | components forming the dispersed particles or droplets |
| particle_density_kg_m3 | number | kg/m³ | required | true particle density |
| particle_diameter_m | number | m | one form required | monodisperse size |
| d_rr_m, n_rr | number | m, – | one form required | Rosin-Rammler by mass |
| inlet_width_m, inlet_height_m | number | m | required | W, H |
| body_length_m, cone_length_m | number | m | required unless N_e | L_b, L_c |
| N_e | number | – | from H2 | effective turns |
| outlet_diameter_m | number | m | required unless dP | D_e |
| K_inlet | number | – | 16 | Shepherd-Lapple constant |
| fluid_underflow_fraction | number | – | 0 | R_f |
| dP | number | Pa | H6 | overrides the computed drop |
| fluid_viscosity_Pa_s | number | Pa·s | phase value | override |

```yaml
type: object
required: [particle_components, particle_density_kg_m3, inlet_width_m, inlet_height_m]
properties:
  particle_components: {type: array, items: {type: string}, minItems: 1, description: 'component ids forming the particles/droplets'}
  particle_density_kg_m3: {type: number, exclusiveMinimum: 0, description: 'particle density, kg/m3'}
  particle_diameter_m: {type: number, exclusiveMinimum: 0, description: 'monodisperse particle diameter, m'}
  d_rr_m: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler characteristic size, m'}
  n_rr: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler spread'}
  inlet_width_m: {type: number, exclusiveMinimum: 0, description: 'inlet width W, m'}
  inlet_height_m: {type: number, exclusiveMinimum: 0, description: 'inlet height H, m'}
  body_length_m: {type: number, exclusiveMinimum: 0, description: 'cylinder length Lb, m'}
  cone_length_m: {type: number, exclusiveMinimum: 0, description: 'cone length Lc, m'}
  N_e: {type: number, exclusiveMinimum: 0, description: 'effective turns; default (Lb + Lc/2)/H'}
  outlet_diameter_m: {type: number, exclusiveMinimum: 0, description: 'vortex finder diameter De, m'}
  K_inlet: {type: number, exclusiveMinimum: 0, description: 'Shepherd-Lapple inlet constant; default 16 (tangential)'}
  fluid_underflow_fraction: {type: number, minimum: 0, exclusiveMaximum: 1, description: 'fluid flow split to the underflow'}
  dP: {type: number, minimum: 0, description: 'overflow pressure drop, Pa; default Shepherd-Lapple'}
  fluid_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'fluid viscosity override, Pa s'}
```

## Outputs
- **Ports:** `overflow` and `underflow`, from R0.
- **`info`:** `v_inlet_m_s`, `N_e`, `d50_m`, `overall_efficiency`, `N_H`, `dP_Pa`, `rho_fluid_kg_m3`, `mu_fluid_Pa_s`, `Q_m3_s`, and `underflow_fraction_<cid>` for every feed component.

## Tests
Numbers come from `scratchpad/unit-specs/calc_hydrocyclone.py`.
- **Inputs (pure functions):** a Lapple standard-proportion gas cyclone with D = 0.5 m, giving W = 0.125, H = 0.25, D_e = 0.25, L_b = L_c = 1.0. Q = 0.5 m³/s, ρ_f = 1.2, μ = 1.8e-5, ρ_p = 2000.
- **CF1:** `v_i = 16`, `N_e = 6`, `d50 = 4.09828629e-6 m`; rtol 1e-9.
- **CF2:** `η(5 µm) = 0.598144072`, `η(10 µm) = 0.856194068`; rtol 1e-9.
- **CF3:** `N_H = 8`, `ΔP = 1228.8 Pa`; rtol 1e-12.
- **CF4:** with Rosin-Rammler d_RR = 10 µm and n = 1.5, the GL64 overall efficiency is `0.685967673`, rtol 1e-9. An independent midpoint rule with 2e6 points gives 0.685967816; the 1.4e-7 difference is quadrature, so the test pins GL64.
- **CF5:** with R_f = 0.1, the particle underflow fraction is `0.717370906`; rtol 1e-9.
- **Light-particle branch:** `ρ_p < ρ_f` sends the separated fraction to the overflow, per H7. Assert the formula with E = 0.6 and R_f = 0.2: underflow fraction = 0.08 exactly.
- **Identity:** on the R0 example feed (H2O 0.95, nC5 0.05 at 323.15 K, 0.5 MPa), R1 with `particle_components ["nC5"]`, ρ_p = 700 (oil lighter than water), a monodisperse 50 µm, a small geometry and R_f = 0.9. Then call R0 with `info`'s fractions and `dP_Pa`: the outlets must be `==` R1's.
- **Refusals:** one test per row.
- **V1 candidates:**
  - Cooper & Alley, *Air Pollution Control: A Design Approach* (3rd or 4th ed.), Ch. 4: the Lapple cyclone worked example. It prints the dimensions, flow, densities, viscosity, N_e, d50 and the efficiencies per size.
  - Perry's 8th ed. Sect. 17, the cyclone example.
  - Transcribe printed inputs and printed results only. If no copy can be verified: V1 gap naming these two sources.

## Steps
1. Pure functions (H1–H6, GL64 integration, H7 fractions) plus CF1–CF5 and the light-particle test. Push, then open the PR.
2. The `HydrocycloneR1` adapter, with the identity and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.hydrocyclone_r1:HydrocycloneR1`). Regenerate the docs, then `--audit`. Push.
3. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- d50 exactly as H3, with the 9 and 2π and |Δρ|.
- GL64 only, not adaptive quadrature.
- Particle density is never read from the phases.
- The split is delegated to R0 and its fractions reported.
- The light-particle branch is correct.
- K defaults to 16 and is documented.
