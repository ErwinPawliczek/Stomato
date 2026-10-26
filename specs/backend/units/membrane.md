# membrane R1, R2: Multicomponent solution-diffusion with permeances: cross-flow (R1) and counter-current (R2)

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1, cross-flow (`planned` → `provisional`). R2, counter-current, is built on R1 (`planned` → `provisional`) and is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe with other units. R2 comes after R1 on **the same branch and PR**: it imports R1's local-flux solver.
- **Branch:** `u-lv/membrane` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/membrane_r1.py` (new): `MembraneR1`, `MembraneR1SpecError`, `local_permeate(...)`, `cross_flow(...)`
  - `src/ngdesign/units/separation/membrane_r2.py` (new): `MembraneR2`, `counter_current(...)`
  - `tests/units/separation/test_membrane_r1.py` and `tests/units/separation/test_membrane_r2.py` (new)
  - `data/validation_units/separation/cases/membrane.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` and `levels.R2` of row `membrane`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `scipy.integrate.solve_ivp(fun, t_span, y0, method="DOP853", rtol=..., atol=..., events=...)`
  - `scipy.optimize.brentq(f, a, b, xtol=..., rtol=..., maxiter=...)` and `scipy.optimize.root(fun, x0, method="hybr", tol=..., options={"maxfev": ...})`
  - `ngdesign.units._physics.splitting.split_by_component(state, fractions, thermo, outlet_T=None, outlet_P=None)` (the R0 outlet pattern)
  - `ngdesign.units.separation.membrane.Membrane` (R0, read-only)
- **Current state:**
  - R0 is either a `permeate_recovery` split or the binary Weller-Steiner complete-mixing `stage_cut` with `perm_ratio`.
  - The permeate leaves at `P_permeate`, the residue at P_in, both at the feed T.
  - V1 already exists: Geankoplis Ex. 13.4-2, complete mixing.

## Method
### Equations (SI)
Sources:
- Weller & Steiner, J. Appl. Phys. 21:279 (1950), complete mixing and cross-flow;
- Pan, C. Y., AIChE J. 29(4):545 (1983), multicomponent cross-flow and counter-current hollow fibre;
- Geankoplis, 4th ed., §13.4–13.5;
- Baker, *Membrane Technology and Applications*, Ch. 8.

Notation: feed-side pressure P_h (the inlet P); permeate pressure P_l (`P_permeate`); permeance Π_i in mol/(m²·s·Pa), where 1 GPU = 3.348e-10 mol/(m²·s·Pa).
- **M1 Flux:** `J_i = Π_i·(P_h·x_i − P_l·y_i)`, with x the local feed-side and y the local permeate-side composition.
- **M2 Cross-flow local permeate** (the permeate leaves where it forms, with no mixing along the membrane): `y_i = J_i/ΣJ`.
  - With `S = ΣJ`, this gives `y_i = Π_i·P_h·x_i/(S + Π_i·P_l)`, where S solves `Σ y_i(S) = 1`.
  - The sum decreases in S. It is above 1 at S = 0 (it equals P_h/P_l there) and at most 1 at `S_hi = Σ Π_i·P_h·x_i`, so the root is bracketed.
  - At P_l = 0: `S = Σ Π_i·P_h·x_i` directly.
- **M3 Cross-flow (R1) feed-side balance along the area a ∈ [0, A]:** `dn_i/da = −S(x)·y_i(x)`, with `x_i = n_i/Σn` and `n_i(0) = F·z_i`.
  - Permeate total: `p_i = F·z_i − n_i(A)`.
  - Stage cut: `θ = Σp/F`.
- **M4 Counter-current (R2), Pan 1983 with a plug-flow permeate flowing toward the feed end.** The permeate collected at the feed end (a = 0) is the permeate product.
  - Feed side: `dn_i/da = −J_i`.
  - Permeate side: `dp_i/da = −J_i`, with `p_i(A) = 0`, so the permeate flows toward a = 0.
  - The local permeate-side bulk composition is `y_i = p_i/Σp`.
  - At the residue end, where Σp = 0, y is the cross-flow limit of M2. Switch to M2 whenever `Σp ≤ 1e-12·F`.
  - Boundary-value problem: unknowns `r_i = n_i(A)`, the residue flows (N unknowns). Integrate from a = A to a = 0 and require `n_i(0) = F·z_i`, which is N equations.
- **M5 Stage-cut mode:** given θ, find A.
  - R1: a terminal `solve_ivp` event on `Σ(F·z_i − n_i) − θ·F = 0`.
  - R2: `brentq` on `θ_R2(A) − θ`.

### Algorithm (R1)
1. Validate: `permeances_mol_m2_s_Pa` must cover every feed component (all > 0); `P_permeate` must be in (0, P_in); exactly one of `area_m2` and `stage_cut` (θ ∈ (0, 1)).
2. `local_permeate(x, Pi, P_h, P_l) -> (y, S)`:
   - P_l = 0: closed form.
   - Otherwise `brentq` on [0, S_hi] with `xtol = 1e-14·S_hi` and `maxiter = 200`, raising `MembraneR1SpecError` on failure.
3. `cross_flow(F, z, Pi, P_h, P_l, area=None, stage_cut=None)`:
   - `solve_ivp(..., method="DOP853", rtol=1e-11, atol=1e-13·F)` over [0, A];
   - in stage-cut mode, integrate over [0, A_hard] with the event. Set `A_hard = 1e3·θ·F/(Σ_i Π_i·P_h·z_i)`, and refuse "stage cut not achievable" if the event doesn't fire. With P_l > 0, the permeate cannot exceed the pressure-ratio limit.
   - Return the residue flows, the permeate flows, the area and θ.
4. Outlets: `fractions_i = p_i/(F·z_i)`, then `split_by_component(inlet, fractions, thermo, outlet_P={"top": P_l, "bottom": P_h})`. Permeate on top and residue on the bottom, both at the feed T (isothermal, as in R0).
5. `duty_W` is the closure; `power_W = 0`.

### Algorithm (R2)
1. The same validation.
2. **Initial guess:** R1's cross-flow residue at the same area. In stage-cut mode, first find the R1 area for θ.
3. **Shooting:** `scipy.optimize.root(residual, r0, method="hybr", tol=1e-12, options={"maxfev": 200})`.
   - `residual(r)` integrates M4 from A to 0 with `solve_ivp(DOP853, rtol=1e-11, atol=1e-13·F)` and returns `n(0) − F·z`.
   - Refuse with `MembraneR1SpecError("counter-current shooting did not converge")` if not converged or `max|residual| > 1e-9·F`.
4. **Stage-cut mode:** `brentq` on `θ_R2(A) − θ` over [0, A_R1(θ)]. If `θ_R2(A_R1) < θ`, double the bracket up to 10 times, then refuse. `xtol = 1e-12·A`, `maxiter = 100`.
5. Outlets as in R1 step 4. The permeate is `p_i(0)`.

### Reduction to the lower level
- **R1 → R0:** with equal permeances for every component, `y = x = z` everywhere. R1 then equals R0 with `permeate_recovery = {cid: θ}` for every component, where θ is R1's stage cut. Tolerance: relative 1e-9 on every outlet component flow (integration tolerance).
- **R2 → R1:** with `P_permeate` → 0 the permeate side has no effect. Test at `P_permeate = 1e-6·P_h`, and also exactly in the pure functions with `P_l = 0`. R2 equals R1 at the same area to relative 1e-8.

### Refusals (`MembraneR1SpecError(ValueError)`, also used by R2)
| Condition | Message fragment |
|---|---|
| `permeances_mol_m2_s_Pa` missing a feed component, naming one not in the feed, or with an entry ≤ 0 | `permeances_mol_m2_s_Pa` |
| `P_permeate` missing, ≤ 0 or ≥ P_in | `P_permeate` |
| both or neither of `area_m2` and `stage_cut` | `area_m2` |
| `area_m2` ≤ 0, or `stage_cut` outside (0, 1) | the parameter name |
| stage cut not reached by `A_hard` | `not achievable` |
| local brentq failure, or R2 shooting failure | `did not converge` |

## Params (R1 and R2 identical)
```yaml
type: object
required: [permeances_mol_m2_s_Pa, P_permeate]
properties:
  permeances_mol_m2_s_Pa: {type: object, description: 'component id to permeance, mol/(m2 s Pa) (1 GPU = 3.348e-10); every feed component required'}
  P_permeate: {type: number, exclusiveMinimum: 0, description: 'permeate-side absolute pressure, Pa'}
  area_m2: {type: number, exclusiveMinimum: 0, description: 'membrane area, m2 (rating mode)'}
  stage_cut: {type: number, exclusiveMinimum: 0, exclusiveMaximum: 1, description: 'target permeate/feed molar ratio (design mode; area is solved)'}
```

## Outputs
- **Ports:** `permeate` and `residue`, as in R0.
- **`info`:** `area_m2`, `stage_cut`, `permeate_y_<cid>`, `residue_x_<cid>`; R2 adds `shooting_nfev`.

## Tests
Reference numbers come from `scratchpad/unit-specs/calc_membrane.py`: hand-written RK4 (20,000 steps) plus bisection and Newton, with no scipy and no ngdesign. Common inputs: binary O2/N2, z = (0.209, 0.791), F = 1 mol/s, P_h = 1e6 Pa, Π_O2 = 5e-9, Π_N2 = 5e-10 (α = 10).
- **CF1 (R1, P_l = 0, Rayleigh closed form `n_O2/n_O2,0 = (n_N2/n_N2,0)^α`):** θ = 0.2 → residue `x_O2 = 0.10094162`, permeate `y_O2 = 0.641233521`; rtol 1e-7, through `cross_flow(..., stage_cut=0.2)`. The area found is `A = 169.155932 m²` (rtol 1e-6).
- **CF2 (R1, P_l = 1e5, A = 100):** `θ = 0.100888989`, `y_O2 = 0.615516887`, `x_O2 = 0.163384857`; rtol 1e-7.
- **CF3 (R2, P_l = 1e5, A = 100):** `θ = 0.101547682`, `y_O2 = 0.61873158`, `x_O2 = 0.162690039`; rtol 1e-7. This is the same answer at 4,000 and 16,000 RK4 steps. Counter-current beats cross-flow, as it should.
- **CF4 (R2 = R1 at P_l = 0, A = 100):** `θ = 0.128104867`, `y_O2 = 0.67743863`, `x_O2 = 0.140173754`. Both levels match; rtol 1e-7.
- **`local_permeate` check at P_l > 0:** the y it returns satisfies `Σy = 1` to 1e-14, and `J_i = S·y_i` equals `Π_i(P_h·x_i − P_l·y_i)` to 1e-12.
- **Identity:** R1 against R0 with equal permeances, on the R0 example feed with `area_m2` 50 and Π = 1e-9 for both O2 and N2. R2 against R1 at `P_permeate = 1e-6·P_h`.
- **Unit-level:** the R0 example feed (air, 2.533e5 Pa, permeate at 2.533e4 Pa) with Π_O2 = 10·Π_N2 and stage cut 0.2. R1's permeate `y_O2` must exceed R0's complete-mixing 0.5068, because cross-flow beats complete mixing. Balances: moles at 1e-12, energy at 1e-8.
- **Refusals:** one test per row. For "not achievable" use θ = 0.95 with P_h/P_l = 1.5 and α = 10.
- **V1 candidates:**
  - Geankoplis, 4th ed., §13.5, the cross-flow worked example. If it uses the Ex. 13.4-2 air case at θ = 0.2, α = 10 and a pressure ratio of 10, its printed y_p and x_o are directly comparable to R1. Corroborate with the FOSSEE transcription, GeankoplisChapter13, as for the R0 case.
  - Pan (1983) prints multicomponent cases as tables or figures; a figure-only result is not V1.
  - If not verifiable: V1 gap naming Geankoplis §13.5, Pan 1983, and Baker Ch. 8.

## Steps
1. `local_permeate` and `cross_flow` plus CF1 and CF2 and the local check. Push, then open the PR.
2. The `MembraneR1` adapter, with the R1 identity, unit-level and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.membrane_r1:MembraneR1`). Regenerate the docs, then `--audit`. Push.
3. `counter_current` (shooting) plus CF3 and CF4. Push.
4. The `MembraneR2` adapter, with the R2 identity and stage-cut tests. Flip the catalogue R2. Regenerate the docs, then `--audit`. Push.
5. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- M2's root is bracketed and capped, with the closed form at P_l = 0.
- The integration tolerances are as specified.
- R2's boundary condition is `p(A) = 0`, integrated backward, with the y switch at Σp ≈ 0.
- The R2 initial guess comes from R1.
- Stage-cut events and brackets are capped, with typed errors.
- Outlets go through `split_by_component` (isothermal), like R0.
