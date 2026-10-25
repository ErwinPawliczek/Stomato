# double_pipe R1: single-phase rating, Gnielinski tube and annulus, counterflow ε-NTU

- **Family / package:** heat, `src/ngdesign/units/heat/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`.
- **Depends on:**
  - the U-R2 conventions;
  - U-01d (#243);
  - **T-PP**, an orchestrator prerequisite. `Thermo.phase_props` must return `viscosity` and `thermal_conductivity`. Today `ngdesign/thermo/_state.py::_single_phase_object` builds the phase with `Phase.to()`, which drops the flasher's `correlations`, so `mu()`/`k()` fail and come back as `None` on `pr`. Verified 2026-10-25: with the correlations re-attached, `pr` gives water k = 0.6371 and μ = 5.768e-4 at 320 K / 3 bar, N₂ k = 0.03304 at 400 K / 10 bar, and air k = 0.02608 at 300 K. This thread must not edit `thermo/`. If T-PP is not on main when you start, post `BLOCKED:` on the issue.
- **Wave/order:** first in the heat wave. This unit **owns the shared rating core** `units/heat/rating.py`; shell_tube, plate_exchanger and air_cooler run after it and import from it read-only.
- **Branch:** `u-lv/double_pipe` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/heat/rating.py` (new; shared rating core);
  - `src/ngdesign/units/heat/double_pipe_r1.py` (new; adapter `DoublePipeR1`);
  - `tests/units/heat/test_rating.py`, `tests/units/heat/test_double_pipe_r1.py` (new);
  - `data/validation_units/heat/cases/double_pipe.yaml` (new);
  - the `levels.R1` entry of row `double_pipe` in `data/unit_models/heat.yaml`, plus the row `notes` line if a V1 gap is recorded.
- **Read-only imports (verified, `ht` 1.2.0 / `fluids` 1.3.1):**
  - `fluids.friction_factor(Re: float, eD: float = 0.0, Method: str | None = 'Clamond', Darcy: bool = True) -> float`. Clamond solves Colebrook to machine precision.
  - `ht.turbulent_Gnielinski(Re: float, Pr: float, fd: float) -> float`
  - `ht.effectiveness_from_NTU(NTU, Cr, subtype='counterflow', n_shell_tube=None)`
  - `scipy.optimize.brentq`
  - `ngdesign.units._physics.heat_balance.TemperatureCross`, `two_stream`, `TwoStreamSpec` (the latter two for the identity test only)
  - `ngdesign.sizing.lmtd.lmtd_counter(Th_in, Th_out, Tc_in, Tc_out) -> float`
  - `ngdesign.contracts.PhaseKind` (`VAPOR`, `HC_LIQUID`, `AQUEOUS`, `SOLID`)
  - `Thermo.phase_props(composition, T, P, kind) -> PhaseProps`, with `density` (kg/m³), `viscosity` (Pa·s), `thermal_conductivity` (W/m/K), `cp` (J/mol/K) and `molecular_weight` (g/mol)
  - `Thermo.flash_ph`, `Thermo.flash_pt`
- **Current state:**
  - R0 is `ngdesign.units.heat.exchangers:DoublePipeExchanger`.
  - Ports: `hot_in`, `cold_in` → `hot_out`, `cold_out`.
  - It runs `two_stream` with exactly one of `duty_W` / `hot_T_out` / `cold_T_out` / `min_approach_K`.
  - info keys: `duty_W`, `LMTD_K`, `lmtd_valid`, `min_approach_K`, `UA_W_K`.
  - V1 V2082 is Kern Example 6.1, assessed.

## Method

### Equations
Every quantity is SI.
1. Film properties are evaluated at the bulk mean state of each side: T̄ = (T_in + T_out)/2 and P̄ = (P_in + P_out)/2, in the inlet's single phase kind.
   - cp_mass = cp/(MW/1000), and Pr = cp_mass·μ/k.
2. Duct flow: v = ṁ/(ρ·A_flow), Re = ρ·v·D_h/μ.
   - Inner pipe: A_flow = π·D_i²/4 and D_h = D_i.
   - Annulus: A_flow = π(D_o,shell² − D_o,tube²)/4 and D_h = D_o,shell − D_o,tube. This is the hydraulic-diameter approach of Incropera et al., *Fundamentals of Heat and Mass Transfer*, 7th ed., §8.7. The Gnielinski 2009 annulus correction is deliberately omitted, so state that in the docstring.
3. Darcy friction:
   - f_D = 64/Re for Re < 2300 (Incropera eq. 8.19);
   - otherwise the Colebrook root (Colebrook 1939; Incropera eq. 8.20), through `fluids.friction_factor(Re, eD)`.
4. Nusselt number:
   - Nu = 3.66 for Re < 2300 (fully developed laminar, constant wall temperature; Incropera eq. 8.55);
   - otherwise Gnielinski: Nu = (f_D/8)(Re − 1000)Pr / [1 + 12.7(f_D/8)^½(Pr^⅔ − 1)] (Gnielinski 1976; Incropera eq. 8.62), through `ht.turbulent_Gnielinski`.
   - Then h = Nu·k/D_h.
5. Overall U, referenced to the inner tube's OUTSIDE area A_o = π·D_o,tube·L:
   1/U_o = 1/h_o + R_fo + D_o·ln(D_o/D_i)/(2k_w) + R_fi·D_o/D_i + D_o/(D_i·h_i)
   (Incropera eq. 11.5 with the fouling terms of Table 11.1's convention).
6. Counterflow ε-NTU: C_h = Q/(T_h,in − T_h,out) and C_c = Q/(T_c,out − T_c,in), from the actual enthalpy change, so they are not constant-cp approximations. NTU = UA/C_min, C_r = C_min/C_max.
   - ε = [1 − e^(−NTU(1−C_r))]/[1 − C_r·e^(−NTU(1−C_r))], or NTU/(1 + NTU) at C_r = 1 (Incropera eqs. 11.29a/b).
   - Q = ε·C_min·(T_h,in − T_c,in) (Incropera eq. 11.21).
7. Pressure drop per side: ΔP = f_D·(L/D_h)·ρv²/2 (Darcy-Weisbach), evaluated with **inlet-state** properties. That keeps ΔP explicit, with no ΔP–property loop.

### Algorithm (`rating.rate_two_stream` plus the adapter)
1. Validate the params against the refusal table. Refuse if any inlet has zero flow, or if T_h,in ≤ T_c,in (`TemperatureCross`).
2. Single-phase check on the inlets: each inlet must have exactly one phase (`len(state.phases) == 1`). Otherwise raise `SinglePhaseRequired`, naming the side.
3. Compute ΔP for each side from inlet properties (Eq. 7) by calling `phase_props` at the inlet T and P. Then P_h,out = P_h,in − ΔP_h and P_c,out = P_c,in − ΔP_c. A P_out ≤ 0 is refused.
4. Find Q_max = min(F_h·(h_h,in − h_h(T_c,in, P_h,out)), F_c·(h_c(T_h,in, P_c,out) − h_c,in)) with two `flash_pt` calls.
5. Define g(Q):
   - outlets by `flash_ph(z, P_out, h_in ∓ Q/F, F)`;
   - each outlet's vapour fraction must equal its inlet's within 1e-6, else `SinglePhaseRequired`, naming the side and Q;
   - UA = U_o(film props at the side means)·A_o;
   - C_h, C_c from Eq. 6 (as Q → 0, use F·cp_mass·MW/1000 at the inlet);
   - g(Q) = Q − ε(NTU, C_r)·C_min·(T_h,in − T_c,in).
6. g(Q_lo = 1e-6·Q_max) < 0 and g(Q_max) > 0 always, because ε < 1 and C_min·ΔT_max ≤ Q_max. Solve with `brentq(g, Q_lo, Q_max, xtol=1e-12*Q_max, maxiter=100)`.
   - If `RuntimeError` or no convergence, raise `RatingConvergenceError` with the last Q and the bracket.
   - If g(Q_max) ≤ 0 within round-off, return Q_max.
7. The converged outlets are `flash_ph` at the converged Q. info as below. `UnitResult.duty_W` = Σ F·h out − Σ F·h in (the R0 convention: the round-off residual of an internal exchanger); `power_W` = 0.
8. The adapter ignores `params["model"]` and `params["mode"]`, which the dispatcher passes through unchanged.

### Reduction to the lower level
Run R0 (`two_stream` with `TwoStreamSpec(duty_W=Q_R1)`, `dP_hot=ΔP_h`, `dP_cold=ΔP_c`) on the same inlets:
- the R0 outlets equal the R1 outlets: T and h to 1e-10 relative, since it is the same `flash_ph` call on the same h and P;
- R0's `UA_W_K` (Q/LMTD) equals R1's `UA_W_K` to 1e-3 relative on the N₂/N₂ example case. The gap is the cp(T) variation that LMTD-UA does not see. Record the measured value in the test docstring.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| a geometry value missing or ≤ 0 | `DoublePipeGeometryError(ValueError)` (in `double_pipe_r1.py`) | the param name |
| `inner_OD_m ≤ inner_ID_m` or `outer_ID_m ≤ inner_OD_m` | `DoublePipeGeometryError` | "inner_OD_m" / "outer_ID_m" |
| `inner_side` ∉ {"hot", "cold"} | `DoublePipeGeometryError` | "inner_side" |
| a side with zero flow | `RatingError(ValueError)` (in `rating.py`) | "needs both streams flowing" |
| T_h,in ≤ T_c,in | `TemperatureCross` (existing) | "inlet temperatures" |
| an inlet or outlet that is not single phase | `SinglePhaseRequired(RatingError)` | "R1 rates single-phase duty", plus the side |
| `phase_props` returning `viscosity` or `thermal_conductivity` as None | `PropertyUnavailable(RatingError)` | the property, the side and the package |
| ΔP that leaves P_out ≤ 0 | `RatingError` | "non-positive outlet pressure" |
| brentq failure | `RatingConvergenceError(RatingError)` | "rating did not converge" |

## Params
| Name | Type | Unit | Required/default | Range | Meaning |
|---|---|---|---|---|---|
| `inner_ID_m` | number | m | required | > 0 | inner pipe inside diameter |
| `inner_OD_m` | number | m | required | > inner_ID_m | inner pipe outside diameter |
| `outer_ID_m` | number | m | required | > inner_OD_m | outer pipe inside diameter |
| `length_m` | number | m | required | > 0 | total effective exchange length (all hairpin legs) |
| `inner_side` | string | – | required | hot/cold | which stream flows in the inner pipe |
| `k_wall_W_mK` | number | W/m/K | 45.0 | > 0 | wall conductivity (carbon steel order of magnitude) |
| `R_f_inner_m2K_W` | number | m²K/W | 0.0 | ≥ 0 | inside fouling resistance |
| `R_f_outer_m2K_W` | number | m²K/W | 0.0 | ≥ 0 | outside fouling resistance |
| `roughness_m` | number | m | 4.5e-5 | ≥ 0 | absolute roughness (commercial steel, Moody 1944) |

```yaml
type: object
required: [inner_ID_m, inner_OD_m, outer_ID_m, length_m, inner_side]
properties:
  inner_ID_m: {type: number, description: 'inner pipe inside diameter, m'}
  inner_OD_m: {type: number, description: 'inner pipe outside diameter, m'}
  outer_ID_m: {type: number, description: 'outer pipe inside diameter, m'}
  length_m: {type: number, description: 'total effective exchange length, m'}
  inner_side: {type: string, enum: [hot, cold], description: 'stream in the inner pipe'}
  k_wall_W_mK: {type: number, description: 'wall conductivity, W/(m K), default 45'}
  R_f_inner_m2K_W: {type: number, description: 'inside fouling, m2 K/W, default 0'}
  R_f_outer_m2K_W: {type: number, description: 'outside fouling, m2 K/W, default 0'}
  roughness_m: {type: number, description: 'absolute roughness, m, default 4.5e-5'}
```

## Outputs
- **Ports:** `hot_out` and `cold_out`, by `flash_ph` at the converged Q and the ΔP-reduced pressures.
- **`duty_W`:** the R0 convention (Σ out − Σ in, round-off level). **`power_W`:** 0.
- **info:**
  - `duty_W` (heat transferred hot → cold, W), `U_W_m2K`, `A_m2`, `UA_W_K`, `NTU`, `effectiveness`, `LMTD_K`;
  - `h_inner_W_m2K`, `h_annulus_W_m2K`, `Re_inner`, `Re_annulus`;
  - `dP_inner_Pa`, `dP_annulus_Pa`, `rating_iterations`.

## `rating.py` public API (shared with shell_tube, plate_exchanger and air_cooler; exact names)
- **Errors:** `RatingError(ValueError)`, `SinglePhaseRequired(RatingError)`, `PropertyUnavailable(RatingError)`, `RatingConvergenceError(RatingError)`.
- **Film properties:**
  - `@dataclass(frozen=True) FilmProps(rho_kg_m3, mu_Pa_s, k_W_mK, cp_J_kgK)` with a `Pr` property;
  - `film_props(thermo, z, T, P, kind) -> FilmProps`, which raises `PropertyUnavailable`;
  - `inlet_kind(state) -> PhaseKind`, which raises `SinglePhaseRequired` unless the state has exactly one phase.
- **Duct correlations:**
  - `darcy_friction(Re, eD) -> float`
  - `nu_tube(Re, Pr, fd) -> float`
  - `duct_h(m_kg_s, flow_area_m2, Dh_m, props, roughness_m) -> DuctResult(h_W_m2K, Re, v_m_s, fd)`
  - `darcy_dP(fd, L_m, Dh_m, rho, v) -> float`
- **Wall:** `u_outside_tube(h_i, h_o, Do, Di, k_wall, R_fi, R_fo) -> float`
- **Solver:** `rate_two_stream(hot, cold, thermo, P_h_out, P_c_out, ua_of, eps_of) -> RatedTwoStream(hot_out, cold_out, duty_W, UA_W_K, NTU, effectiveness, iterations)`.
  - `ua_of(hot_out, cold_out) -> float` and `eps_of(NTU, Cr) -> float` are supplied by the unit (counterflow here; `'S&T'` for shell_tube).

## Tests
- **Closed-form** (`test_rating.py`, pure functions, independent numbers from `calc_double_pipe.py`):
  1. **Tube, turbulent:** ṁ 0.5 kg/s, D_i 0.0266 m, ρ 990, μ 5.77e-4, k 0.637, cp 4180, ε 4.5e-5 m.
     - Expect v = 0.908827909 m/s, Re = 41478.4647, Pr = 3.78627943, f_D = 0.0263385704, Nu = 247.163932, h = 5918.92574 W/m²K.
     - ΔP over 6 m = 2429.0157 Pa.
     - Tolerance rel 1e-8.
  2. **Laminar:** ṁ 0.02, ρ 900, μ 0.05, k 0.13 in the same pipe. Expect Re = 19.1464593, Nu = 3.66, h = 17.887218, f_D = 64/Re = 3.34265458.
  3. **Annulus:** D_o,tube 0.0334, D_i,shell 0.0525; N₂ with ṁ 0.3, ρ 8.41, μ 2.22e-5, k 0.0330, cp 1053.7.
     - Expect A = 0.00128859491 m², D_h = 0.0191, Re = 200301.977, f_D = 0.0252700562, Nu = 522.74325, h = 903.168965.
  4. **U_o:** with h_i from case 1, h_o from case 3, k_w 45, R_fi 1.8e-4, R_fo 3.5e-4: U_o = 505.089091 W/m²K.
  5. **ε-NTU:** UA 2000, C_h 1500, C_c 2500, T_h 400 K, T_c 300 K: NTU = 1.33333333, C_r = 0.6, ε = 0.63787956, Q = 95681.934 W. UA·LMTD reproduces Q to 1e-12. At C_r = 1: ε = 0.571428571.
- **Identity** (`test_double_pipe_r1.py`): the reduction above, on the R0 example case (N₂ 500 K / N₂ 320 K, 100 mol/s each, 10 bar), with the geometry inner_ID 0.0266, inner_OD 0.0334, outer_ID 0.0525, length 60 m, inner_side hot.
- **V0:** the harness closes the energy balance at 1e-8 on the example case.
- **Refusals:** one test per refusal-table row, each with `pytest.raises(..., match=...)`. A two-phase inlet (water at its bubble point) must reach `SinglePhaseRequired`.
- **V1 candidates:**
  - Kern (1950), *Process Heat Transfer*, Example 6.1: benzene/toluene, 2 × 1¼ in IPS, 20-ft hairpins. It prints the inputs and the computed h_io, h_o, clean and design U, and both pressure drops; the R0 row already runs its inputs as V2082.
  - Transcribe the printed film coefficients and pressure drops as `info` quantities.
  - Kern reads j_H from Sieder–Tate charts, not Gnielinski, so expect misses of order 10–20 % and record them as `assessed` with the measured numbers. Never widen.
  - Use `thermo: pr-peneloux` on the case, since PR without volume translation underpredicts liquid density by about 15 %. First confirm that its `phase_props` returns μ and k.

## Steps
1. `rating.py`: the errors, `FilmProps`/`film_props`/`inlet_kind`, `darcy_friction`, `nu_tube`, `duct_h`, `darcy_dP`, `u_outside_tube`, with closed-form tests 1–4. Push.
2. `rating.rate_two_stream`: the brentq solve, plus closed-form test 5 (wrap it in a test that uses a fake constant-cp `Thermo`, where h = cp·T, so the solver must return the analytic ε-NTU Q to 1e-9). Push.
3. `double_pipe_r1.py`: the adapter and `example_case` (the R0 feeds plus the geometry above); the identity test, the refusal tests and the YAML `levels.R1` entry. Push.
4. The V1 case file (Kern 6.1) or a recorded gap, then the harness write-doc and `--audit` as separate runs. Push and request review.

## Review checklist
- Eq. 4 switches at Re = 2300 with no hidden transition blend. Gnielinski is called with the **Darcy** f.
- ΔP uses inlet properties, as specified, with no extra loop.
- C_h and C_c come from enthalpy differences, not cp.
- The brentq bracket signs are as stated: xtol 1e-12·Q_max, maxiter 100, and a typed error on failure.
- The single-phase check runs on both inlets and on the outlets at every g evaluation.
- `rating.py` has no unit-specific logic. Its API matches the list above exactly, since three other threads import it.
- The `model` key is ignored, and R0 remains the default level.
