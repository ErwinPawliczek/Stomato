# pipe_segment R1, R2: Darcy–Colebrook marching with elevation; Beggs–Brill two-phase profile

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:**
  - R1 (single-phase Darcy–Colebrook with elevation, marched along the length), from `planned` to `provisional`;
  - R2 (two-phase Beggs–Brill with a profile, built on R1's marcher), from `planned` to `provisional`. R2 is the row's end state.
- **Depends on:** U-R2 conventions, U-01d. R2 is built after R1 in the same branch.
- **Wave/order:** parallel-safe. It shares no owned file.
- **Branch:** `u-lv/pipe_segment` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/pipe_segment_r1.py` (new), holding the marcher core and the R1 adapter;
  - `src/ngdesign/units/flow/pipe_segment_r2.py` (new), holding the R2 adapter, which imports the R1 core;
  - `tests/units/flow/test_pipe_segment_r1.py` and `tests/units/flow/test_pipe_segment_r2.py` (new);
  - `data/validation_units/flow/cases/pipe_segment.yaml` (new);
  - in `data/unit_models/flow.yaml`, row `pipe_segment`: the `levels.R1` and `levels.R2` entries, plus the `notes` line for V1 gaps.
- **Read-only imports (verified, fluids 1.3.1):**
  - `ngdesign.sizing.line_friction.darcy_colebrook(Q_m3_s, D_m, rho, mu, roughness_m, L_m) -> {velocity_m_s, Re, darcy_f, dP_Pa}`. It uses f = 64/Re below Re 2300 and `fluids.friction.Colebrook` above, and requires Q > 0 and L > 0. It is the repo's one owner of single-phase friction.
  - `fluids.two_phase.Beggs_Brill(m, x, rhol, rhog, mul, mug, sigma, P, D, angle, roughness=0.0, L=1.0, g=9.80665, acceleration=True) -> float` returns the ΔP over L in Pa, with `angle` in **degrees** from horizontal. This implementation uses the original Beggs & Brill (1973) holdup with the Brill–Beggs transition interpolation, Moody/Clamond `friction_factor` with roughness, and **no Payne correction**. It raises a plain `ValueError("Outside regime ranges")`, which must be wrapped.
  - `ngdesign.units.flow.pipe_segment.PipeSegment`, `PipeSegmentSpecError`, `G_STD` (R0, read-only).
  - `Thermo.flash_ph`, `Thermo.phase_props`.
- **Current state (R0):** `ngdesign.units.flow.pipe_segment:PipeSegment`, ports `inlet -> outlet`.
  - Exactly one of `dP`/`P_out` is given, plus `elevation_m` (default 0).
  - Isenthalpic PH flash. In `dP` mode, `P_out = P_in − dP − ρ·g·z`, with ρ the inlet dominant phase density.
  - info: `dT_K`, `hydrostatic_Pa`.

## Method
### Equations
1. **Momentum, steady 1-D, single phase, acceleration neglected** (valid while the velocity head is small; see the R1 refusal on ΔP/P below):
   `dP/dx = −f/D · G²/(2ρ(P)) − ρ(P)·g·sin θ`, with mass flux `G = ṁ/A`, `A = πD²/4`, and `sin θ = Δz/L` for a straight segment of uniform slope.
   - f is the Darcy friction factor from Colebrook (1939): `1/√f = −2·log10(ε/(3.7D) + 2.51/(Re·√f))`, with `Re = G·D/μ`, and f = 64/Re for Re < 2300. Both come from `darcy_colebrook`.
   - Fittings: `ΔP_K = ΣK·G²/(2ρ_in)`, applied at the inlet (Crane TP-410, the K method).
2. **Energy:** adiabatic and isenthalpic. Each node's state is `flash_ph(z, P_node, h_in, F)`. Potential and kinetic energy are not booked into the enthalpy balance, as in R0. V0 closes exactly, and the error is g·Δz ≈ 0.1 kJ/kg per 10 m.
3. **Integration:** Heun's method (explicit trapezoid) over N equal segments. On each segment of length h:
   - `k1 = F(P_i)`, `P* = P_i + h·k1`, `k2 = F(P*)`, `P_{i+1} = P_i + h(k1 + k2)/2`;
   - F(P) evaluates ρ and μ from `flash_ph(z, P, h_in, F)` at that pressure.
4. **Refinement (R1):** start with N = `n_segments` (default 10). Double N until `|P_out(N) − P_out(N/2)| ≤ 1e-6·(P_in − P_out(N))`, or raise `PipeSegmentR1Error` past N = 1024.
5. **R2 two-phase step:** on segments where the node is two-phase (0.001 < vf < 0.999), the step's ΔP is `Beggs_Brill(m, x, ρl, ρg, μl, μg, σ, P, D, angle=degrees(asin(Δz/L)), roughness=ε, L=h, acceleration=True)`.
   - x is the vapour **mass** fraction from the flash phases, and the phase properties come from the flashed state.
   - Single-phase segments use the R1 Darcy step, so a line can flash part-way along.
   - Integration is the same Heun predictor-corrector with a fixed N (`n_segments`, default 20, cap 200). R2 does not auto-refine, because regime switches make the refinement norm non-smooth. It reports `dP_check_N_half_Pa`, the outlet difference against N/2 (one extra pass), so the discretisation error is visible.
   - σ (surface tension) is **required** when any node is two-phase: the Thermo protocol has no surface tension, so `sigma_N_m` is a param.

### Algorithm
**Core** (pure, module-level in `pipe_segment_r1.py`, injectable for tests):
- `march(P_in, L, D, dz, eps, mdot, props: Callable[[float], tuple[float, float]], n: int) -> float` takes `props(P) -> (rho, mu)`.
- `march_refined(...) -> tuple[float, int]` returns `(P_out, N_used)`.
- The R1 adapter passes a `props` that calls `thermo.flash_ph` and refuses on two-phase.

**R1** (class `PipeSegmentR1`):
1. Validate params. Inlet single phase: refuse 0.001 < vf < 0.999 with "two-phase inlet; use R2".
2. Inlet viscosity: the dominant phase's viscosity, else `params["mu_Pa_s"]`, else refuse.
3. `ΔP_K` at the inlet (eq. 1, fittings).
4. `march_refined` from `P_in − ΔP_K`. A node turning two-phase raises `PipeSegmentR1Error` ("flashes to two-phase at x ≈ … m; use R2"). A node pressure ≤ 0 raises "pressure falls to zero".
5. A large-drop guard for vapour inlets: if `P_out/P_in < 0.5`, refuse ("pressure ratio below 0.5: acceleration and choking are not modelled at R1"). For liquid inlets the drop is unrestricted, but P_out must stay above the inlet's bubble pressure (caught by the two-phase check).
6. Outlet `flash_ph(z, P_out, h_in, F)`.
7. Info: `dP_friction_Pa` (integrated friction), `dP_fittings_Pa`, `hydrostatic_Pa` (integrated ρ·g·Δz), `dP_total_Pa`, `velocity_in_m_s`, `Re_in`, `darcy_f_in`, `n_segments_used`, `dT_K`.

**R2** (class `PipeSegmentR2`): same validation, but a two-phase inlet is allowed.
1. Fixed N; Heun with the per-segment step (single-phase Darcy or Beggs–Brill by the node state).
2. Wrap any fluids `ValueError` as `PipeSegmentR2Error` ("Beggs–Brill regime map …").
3. Info: everything in R1's set, plus `n_two_phase_segments`, `dP_check_N_half_Pa`, and the profile keys `profile_<i>_x_m`, `profile_<i>_P_Pa`, `profile_<i>_T_K` and `profile_<i>_quality` for i = 0..N. Keys are zero-padded to 3 digits (`profile_007_P_Pa`) so they sort; info is `dict[str, float]`.

### Reduction to the lower level
- **R1 to R0:** for any R1 solve, the R0 adapter in `dP` mode with `dP = info["dP_friction_Pa"] + info["dP_fittings_Pa"]` and `elevation_m = 0` (a horizontal line) gives the identical outlet state. Both flash at the same P with `h_in`. Assert P exactly and T to 1e-12.
- **R2 to R1:** on an all-liquid line (no node two-phase), `PipeSegmentR2` with `n_segments = N` equals the R1 core `march(…, n=N)` without refinement, to 1e-12 relative on P_out.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `L_m` ≤ 0, `D_m` ≤ 0, `roughness_m` < 0, `K_fittings` < 0 | `PipeSegmentSpecError` (R0, imported) | the name |
| `|elevation_m|` > `L_m` | `PipeSegmentSpecError` | "elevation_m" |
| `n_segments` < 1, or > 200 in R2 | `PipeSegmentSpecError` | "n_segments" |
| R1: two-phase inlet, or a node two-phase | `PipeSegmentR1Error(PipeSegmentSpecError)`, new | "two-phase" |
| R1: vapour P_out/P_in < 0.5 | `PipeSegmentR1Error` | "pressure ratio below 0.5" |
| node P ≤ 0 | `PipeSegmentR1Error` | "pressure falls to zero" |
| refinement past N = 1024 | `PipeSegmentR1Error` | "did not converge" |
| no viscosity | `PipeSegmentSpecError` | "mu_Pa_s" |
| R2: a two-phase node with no `sigma_N_m` | `PipeSegmentR2Error(PipeSegmentSpecError)`, new | "sigma_N_m" |
| R2: Beggs–Brill raises | `PipeSegmentR2Error` | "Beggs–Brill" |
| zero flow | `PipeSegmentSpecError` | "molar_flow" (darcy_colebrook needs Q > 0) |

## Params
| name | type | unit | required/default | range | level | meaning |
|---|---|---|---|---|---|---|
| L_m | number | m | required | > 0 | R1, R2 | length |
| D_m | number | m | required | > 0 | R1, R2 | internal diameter |
| roughness_m | number | m | 4.57e-5 | ≥ 0 | R1, R2 | absolute roughness (commercial steel; Moody 1944) |
| elevation_m | number | m | 0 | \|z\| ≤ L | R1, R2 | outlet elevation minus inlet elevation |
| K_fittings | number | – | 0 | ≥ 0 | R1, R2 | sum of fitting K values (Crane TP-410) |
| n_segments | integer | – | 10 (R1 start) / 20 (R2) | 1..1024 (R1), 1..200 (R2) | R1, R2 | segment count |
| mu_Pa_s | number | Pa·s | none | > 0 | R1, R2 | viscosity override, used when the thermo gives none |
| sigma_N_m | number | N/m | R2 two-phase: required | > 0 | R2 | gas–liquid surface tension |

R1 schema:
```yaml
type: object
required: [L_m, D_m]
properties:
  L_m: {type: number, description: 'length, m'}
  D_m: {type: number, description: 'internal diameter, m'}
  roughness_m: {type: number, description: 'absolute roughness, m, default 4.57e-5'}
  elevation_m: {type: number, description: 'outlet minus inlet elevation, m'}
  K_fittings: {type: number, description: 'sum of fitting resistance coefficients'}
  n_segments: {type: integer, description: 'starting segment count, default 10'}
  mu_Pa_s: {type: number, description: 'viscosity override, Pa.s'}
```
R2 schema: the same, with `n_segments` defaulting to 20 (max 200), plus `sigma_N_m: {type: number, description: 'surface tension, N/m; required if any node is two-phase'}`.

## Outputs
- **Port `outlet`:** `flash_ph(z, P_out, h_in, F)`.
- **Balances:** `duty_W = 0`, `power_W = 0`.
- **info:** as listed in the Algorithm (SI units in the key names).

## Tests
- **Closed-form** (independent script `calc_pipe_segment.py`, with its own Colebrook fixed point):
  - **C1, incompressible liquid**, through `march` with `props = lambda P: (998.0, 1.0e-3)`:
    - inputs D = 0.1023 m, L = 100 m, ε = 4.57e-5 m, ṁ = 10 kg/s, Δz = +10 m, ΣK = 2.5;
    - v = 1.21906906257652 m/s, Re = 124461.343571375, f = 0.0195416887606116;
    - **ΔP_friction = 14165.8821277191 Pa**, hydrostatic = 97870.3670000000 Pa, so `march` gives a ΔP of **112036.249127719 Pa** (P_in − P_out).
    - `march` does not take fittings. A separate assertion on the adapter's fittings helper gives ΔP_fittings = 1853.94640071566 Pa, for an adapter-level **total = 113890.195528435 Pa**.
    - Heun is exact for a constant derivative, so the tolerance is 1e-10.
  - **C2, isothermal ideal gas, horizontal**, with `props = lambda P: (P·M/(R·T), 1.1e-5)`:
    - inputs M = 0.016043, T = 300, P1 = 5.0e6, D = 0.1023, L = 5000, ṁ = 2.0, ε = 4.57e-5;
    - G = 243.326184890273 kg/(m²·s), Re = 2262933.51947954 (constant along the line, so f is constant), f = 0.0165365270433975;
    - the exact solution of eq. 1 is `P1² − P2² = f·G²·R·T·L/(M·D)`, giving **P2 = 4190438.20059489 Pa**;
    - the refined Heun march reproduces it (N = 20, relative error on ΔP 9.7e-8). Test tolerance 1e-6 relative on ΔP.
- **Identity:** R1 to R0 (horizontal line, exact P), and R2 to R1 (all-liquid, fixed N, 1e-12).
- **Unit level:**
  - An n-butane liquid line with a 20 m rise: `hydrostatic_Pa` is within 1e-3 of `ρ_in·g·20` (density varies slightly along the line).
  - A methane gas line at 5 MPa: `dP_total_Pa` agrees with C2's analytic form, evaluated with the inlet-state Z-corrected density, to 2 % (a real gas is not ideal; this is a sanity bound, not a closed form).
- **R2:**
  - A propane/n-pentane line flashing part-way: `n_two_phase_segments` ≥ 1, the profile pressures decrease monotonically, and quality increases.
  - `dP_check_N_half_Pa` is reported.
  - A horizontal segment's step ΔP equals `Beggs_Brill(...)` called by the test with the reported node properties (wiring check, 1e-12).
- **Refusals:** one per refusal row, with `match=`.
- **V1 candidates:**
  - **R1:** Crane TP-410 (2013) chapter 4 examples (water and air through steel pipe, with printed ΔP), and Darby & Chhabra, *Chemical Engineering Fluid Mechanics* (3rd ed., 2017) ch. 6 pipe-flow examples. The implementer transcribes the printed inputs and results. Use `thermo: iapws_if97` for water.
  - **R2:** Brill & Mukherjee, *Multiphase Flow in Wells* (SPE Monograph 17, 1999) ch. 4 Beggs–Brill example, and Shoham (2006) ch. 4 examples. These need a black-oil or PVT basis the thermo may not reproduce, so record misses in `assessed`.
  - V1 gap if they are not accessible, naming the places searched. Never use fluids docstring outputs.

## Steps (each about 40 minutes, each ending in a push)
1. **The `march` and `march_refined` core:** closed-form tests C1 and C2 on injected property functions. Push and open the PR.
2. **The `PipeSegmentR1` adapter:** the thermo-backed `props`, single-phase guard, fittings, the vapour ratio guard, info, refusals, `example_case` (R0's condensate basis with L = 200 m, D = 0.0779 m, elevation 10 m). The R0 identity and the unit-level tests. Push.
3. **The `PipeSegmentR2` adapter:** two-phase step via `Beggs_Brill`, profile keys, the N/2 check, σ refusal, the wrapped regime error, `example_case` (a flashing propane/n-pentane line). The R2 to R1 identity and the R2 tests. Push.
4. **Catalogue `levels.R1` and `levels.R2`** (adapters `ngdesign.units.flow.pipe_segment_r1:PipeSegmentR1` and `...pipe_segment_r2:PipeSegmentR2`, provisional, the schemas, notes "no Payne correction", validation ids). `cases/pipe_segment.yaml` or the gap. Docs and `--audit`, gates, push and comment.

## Review checklist (for the orchestrator)
- Friction goes through `darcy_colebrook` (no second Colebrook).
- Heun predictor-corrector as written, with refinement to 1e-6 of ΔP and a 1024 cap that raises.
- Isenthalpic nodes; no potential energy in the enthalpy balance (V0 exact).
- Beggs–Brill `angle` is passed in **degrees**; x is the **mass** quality; ValueError is wrapped.
- σ is a required param for two-phase (not invented).
- The no-Payne statement is in the module docstring and the catalogue note.
- The identities are exact, not loosened.
- Profile keys are zero-padded floats only.
