# relief_valve R1, R2: omega-method two-phase and liquid relief sizing; inlet loss and back-pressure checks

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:**
  - R1 (two-phase and liquid sizing, with gas by delegation to R0), from `planned` to `provisional`;
  - R2 (inlet-loss and back-pressure checks, built on R1), from `planned` to `provisional`. R2 is the row's end state.
- **Depends on:** U-R2 conventions, U-01d. No other unit spec. R2 is built after R1 in the same branch.
- **Wave/order:** parallel-safe. It shares no owned file.
- **Branch:** `u-lv/relief_valve` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/relief_valve_r1.py` (new), holding the R1 adapter and the omega functions;
  - `src/ngdesign/units/flow/relief_valve_r2.py` (new), holding the R2 adapter, which imports R1;
  - `tests/units/flow/test_relief_valve_r1.py` and `tests/units/flow/test_relief_valve_r2.py` (new);
  - `data/validation_units/flow/cases/relief_valve.yaml` (new);
  - in `data/unit_models/flow.yaml`, row `relief_valve`: the `levels.R1` and `levels.R2` entries, plus the `notes` line for V1 gaps.
- **Read-only imports (verified, fluids 1.3.1):**
  - `ngdesign.units.flow.relief_valve.ReliefValve`, `ReliefValveSpecError`, `LB_PER_H_TO_KG_S`, `R_IDEAL`, `IN2_PER_M2`, `_next_orifice` and `_orifice_area_in2` (R0; gas sizing is delegated to `ReliefValve().solve`);
  - `ngdesign.sizing.psv_gas.api526_orifice(area_in2) -> str`;
  - `ngdesign.sizing.line_friction.darcy_colebrook(Q_m3_s, D_m, rho, mu, roughness_m, L_m) -> {velocity_m_s, Re, darcy_f, dP_Pa}`, which requires L_m > 0 and Q > 0;
  - `fluids.safety_valve.API520_B(Pset, Pback, overpressure=0.1) -> float` (balanced-bellows vapour Kb). **Pressures are absolute in Pa**, converted to gauge inside fluids, and it is valid only below 50 % gauge back pressure;
  - `fluids.safety_valve.API520_W(Pset, Pback) -> float` (balanced-bellows liquid Kw), absolute Pa;
  - `scipy.optimize.brentq`;
  - `Thermo.flash_ph`, `flash_ps`, `flash_tvf`, `bubble_point(z, T=…) -> SaturationPoint(.P)`, `phase_props`.
- **Current state (R0):** `ngdesign.units.flow.relief_valve:ReliefValve`, ports `inlet -> outlet`.
  - Gas only: it refuses `vapor_fraction < 0.999`.
  - Params: `P_back` (required, Pa), plus Kd (0.975), Kb (1.0) and Kc (1.0).
  - API 520 Part I critical gas area via `psv_api520_gas`, with `k = cp/(cp − R)`; the next API 526 orifice.
  - The outlet is an isenthalpic flash at `P_back`.
  - info: `k_ideal`, `required_area_in2`, `selected_orifice_area_in2`.

## Method
### Equations
The omega method: Leung, AIChE J. 32(10):1743–1746 (1986) for two-phase, and Leung, "Easily size relief devices and piping for two-phase flow", Chem. Eng. Prog. 92(12):28–50 (1996) for subcooled liquid. API Standard 520 Part I (10th ed., 2020) Annex C adopts these. The implementer must confirm each equation against the Annex C clause and cite its number in the module docstring; a discrepancy is posted on the PR, not resolved silently.

P0 is the relieving pressure (the inlet P, absolute), Pa the back pressure (`P_back`), and v the specific volume in m³/kg.

1. **Two-phase or saturated inlet, omega parameter:** `ω = 9·(v9/v0 − 1)`.
   - v0 is the mixture specific volume at the inlet (P0, T0).
   - v9 is the specific volume after an **isentropic** flash to 0.9·P0, which is the Annex C preferred option.
2. **Critical pressure ratio η_c** is the root in (0, 1) of `η² + (ω² − 2ω)(1 − η)² + 2ω²·ln η + 2ω²(1 − η) = 0`.
   - Check: ω = 1 gives `1 + 2·ln η = 0`, so η_c = e^(−1/2).
   - Leung's explicit fit, for the test only: `η_c ≈ [1 + (1.0446 − 0.0093431·ω^0.5)·ω^(−0.56261)]^(−0.70356 + 0.014685·ln ω)`.
3. **Mass flux, two-phase:**
   - critical (`Pa/P0 ≤ η_c`): `G = η_c·sqrt(P0/(v0·ω))`;
   - subcritical: `G = sqrt(−2[ω·ln ηa + (ω − 1)(1 − ηa)])·sqrt(P0/v0) / (ω(1/ηa − 1) + 1)`, with ηa = Pa/P0.
   - The two forms coincide at ηa = η_c, which is a continuity test.
4. **Subcooled liquid inlet** (Leung 1996; API 520 Annex C, subcooled):
   - Ps = bubble-point pressure at T0, and ηs = Ps/P0 < 1.
   - `ωs = 9·(ρl0/ρ9 − 1)`, where ρl0 is the inlet liquid density and ρ9 the density after an isentropic flash from saturated liquid at (T0, Ps) to 0.9·Ps.
   - Transition: `η_st = 2ωs/(1 + 2ωs)`.
   - **Low subcooling (ηs ≥ η_st):**
     - η_c is the root in (0, ηs) of `(ωs + 1/ωs − 2)/(2ηs)·η² − 2(ωs − 1)·η + ωs·ηs·ln(η/ηs) + 1.5·ωs·ηs − 1 = 0`;
     - the flow is critical if Pa/P0 < η_c, with η = η_c; otherwise η = ηa;
     - `G = sqrt(2(1 − ηs) + 2[ωs·ηs·ln(ηs/η) − (ωs − 1)(ηs − η)])·sqrt(P0·ρl0) / (ωs(ηs/η − 1) + 1)`.
     - At ηs = 1 the η_c equation divided by 2ω is identical to eq. 2, and G reduces to eq. 3. This was checked algebraically, and numerically to 1e-15.
   - **High subcooling (ηs < η_st):**
     - if Pa < Ps, the flow is choked at Ps: `G = sqrt(2ρl0(P0 − Ps))`;
     - otherwise it is all-liquid (no flashing): `G = sqrt(2ρl0(P0 − Pa))`. This is the API 520 Part I liquid equation in SI; its 11.78 constant is this expression with unit conversions.
5. **Required area:** `A = W/(Kd·Kb·Kc·Kv·Kw·G)` in m², with W in kg/s.
   - Kw applies only to liquid (balanced bellows); Kv is the viscosity correction (user param, default 1).
   - Reported in m², mm² and in² (`IN2_PER_M2` from R0). The API 526 letter is selected from in² as in R0.
6. **R2, rated capacity:** at a fixed relieving state, A ∝ W in every branch above, so `W_rated = W·A_selected/A_required`. API 520 Part II (2015) §7.3.6 and API 521 require inlet losses at the rated capacity.
7. **R2, inlet line loss**, homogeneous, incompressible over a short line (valid when the loss is a few percent of P0, which is exactly what the check enforces):
   - `ΔP_in = f(L/D)·ρm·v²/2 + ΣK·ρm·v²/2`, with `v = W_rated/(ρm·A_pipe)` and f by Darcy–Colebrook (via `darcy_colebrook`, with f = 64/Re below Re 2300).
   - ρm is the inlet mixture density, 1/v0.
   - μm is the inlet viscosity: the single phase's, or the two-phase McAdams form `1/μm = x/μg + (1 − x)/μl` (McAdams, Woods & Heroman, Trans. ASME 64:193, 1942), with x the vapour mass fraction.
   - Check: `ΔP_in ≤ 0.03·(P_set − P_atm)` (API 520 Part II §7.3.6, the 3 % rule).
8. **R2, built-up back pressure** in the discharge line, from the valve outlet to the header at `P_back` (the superimposed back pressure):
   - the outlet-line density is evaluated at the line's mean pressure: `P_mean = P_back + ΔP_out/2`, with the outlet flashed at `P_mean` from `h_in`;
   - fixed point on ΔP_out from 0, `ΔP_out = f(L/D)ρv²/2 + ΣK·ρv²/2` at W_rated;
   - converged when |Δ| ≤ 1e-8·max(ΔP_out, 1 Pa); cap 50 iterations; `ReliefValveR2Error` at the cap.
9. **R2 limits** (API 520 Part I 10th ed. §5.3.3):
   - **conventional:** built-up ≤ 10 % of the set gauge pressure (at 10 % overpressure; the limit equals the `overpressure` param);
   - **balanced bellows:** total back pressure (superimposed + built-up) ≤ 50 % of the set gauge pressure, and the vapour Kb comes from `API520_B(P_set, P_back_total, overpressure)` (Fig. 30), or for a liquid Kw from `API520_W(P_set, P_back_total)` (Fig. 31). The area is then re-sized with that factor and `area_with_backpressure_in2` reported;
   - **pilot:** no limit applies; values are reported and the check reads "not applicable" (`backpressure_ok = 1`).

### Algorithm
**R1** (class `ReliefValveR1`):
1. Validate params (refusal table). Regime by inlet state:
   - **gas** (`vapor_fraction ≥ 0.999`): return `ReliefValve().solve(inlets, r0_params, thermo)` unchanged, adding `regime_code = 0` to info. R0 owns gas sizing.
   - **two-phase** (`0.001 < vf < 0.999`): steps 2–4.
   - **liquid** (`vf ≤ 0.001`): Ps = `thermo.bubble_point(z, T=T0).P`.
     - If Ps ≥ P0·(1 − 1e-9), the liquid is saturated and handled as two-phase (eqs. 1–3) with v0 = 1/ρl0.
     - Otherwise it is subcooled (eq. 4).
2. **v0** from the inlet phases: `v0 = Σ_p (y_p·MW_p/1000)/ρ_p / Σ_p (y_p·MW_p/1000)`, where y_p is the phase mole fraction. Mass-weighted specific volume, from the stream's own phases.
3. **v9:** `s9 = thermo.flash_ps(z, 0.9·P0, inlet.entropy, F)`, then v9 by the same phase rule. ω from eq. 1; refuse if ω ≤ 0.
4. **η_c:** `brentq(eq2, 1e-9, 1 − 1e-12, xtol=1e-14, maxiter=200)`. Then the critical or subcritical G (eq. 3).
5. **Subcooled:**
   - saturated-liquid entropy `s_sat = thermo.flash_tvf(z, T0, 0.0, F).entropy`;
   - `ρ9` from `thermo.flash_ps(z, 0.9·Ps, s_sat, F)` (mass-weighted mixture density);
   - ωs, η_st, then the branch per eq. 4. The low-subcooling η_c uses `brentq` on `(1e-9, ηs·(1 − 1e-12))` with the same caps.
6. Area (eq. 5), API 526 selection via `_next_orifice` and `_orifice_area_in2`.
7. Outlet: `thermo.flash_ph(z, P_back, h_in, F)`, as in R0.

**R2** (class `ReliefValveR2`): run R1. Then `W_rated` (eq. 6), the inlet-line loss (eq. 7) and the back pressure (eqs. 8–9). Report the checks in info. The outlet state is R1's: the checks do not change the process outlet, since the header pressure `P_back` is the boundary.

### Reduction to the lower level
- **R1 to R0:** an all-vapour inlet gives a result identical to R0's (same `UnitResult` values, info being a superset) because R1 delegates to R0. Assert this to 0 difference on R0's `example_case`.
- **R2 to R1:** `L_in_m = 0`, `K_in = 0`, `L_out_m = 0` and `K_out = 0` give `dP_inlet_Pa = 0` and `dP_builtup_Pa = 0`. The outlet and every R1 info value are identical.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `P_back` not in (0, P0) | `ReliefValveSpecError` (R0) | "P_back" |
| Kd, Kb, Kc, Kv or Kw outside (0, 1] | `ReliefValveSpecError` | the name |
| ω ≤ 0 or ωs ≤ 0 | `ReliefValveR1Error(ReliefValveSpecError)`, new | "omega" |
| brentq failure (η_c) | `ReliefValveR1Error` | "critical pressure ratio did not converge" |
| required area above API 526 T | `ReliefValveSpecError` (from R0's `_next_orifice`) | "exceeds the largest API 526 orifice" |
| R2: `P_set` missing, or not in (P_atm, P0] | `ReliefValveR2Error(ReliefValveSpecError)`, new | "P_set" |
| R2: `valve_type` not conventional / balanced_bellows / pilot | `ReliefValveR2Error` | "valve_type" |
| R2: L > 0 with D ≤ 0, or a negative L/K/roughness | `ReliefValveR2Error` | the name |
| R2: bellows back pressure ≥ 50 % gauge (fluids raises) | `ReliefValveR2Error` | "50 %" |
| R2: built-up fixed point at the cap | `ReliefValveR2Error` | "back-pressure iteration" |
| no viscosity for the line loss | `ReliefValveR2Error` | "viscosity" |

## Params
| name | type | unit | required/default | range | level | meaning |
|---|---|---|---|---|---|---|
| P_back | number | Pa abs | required | (0, P0) | R1, R2 | superimposed back pressure at the discharge |
| Kd | number | – | 0.975 gas (R0), **0.85 two-phase**, **0.65 liquid** | (0, 1] | R1 | discharge coefficient; the default is chosen by regime (API 520 Part I: 0.65 liquid; Annex C preliminary 0.85 two-phase). Pass the certified value. |
| Kb | number | – | 1.0 | (0, 1] | R1 | back-pressure correction (vapour / two-phase) |
| Kc | number | – | 1.0 | (0, 1] | R1 | rupture-disk combination factor |
| Kv | number | – | 1.0 | (0, 1] | R1 | viscosity correction (liquid) |
| Kw | number | – | 1.0 | (0, 1] | R1 | liquid back-pressure correction (balanced bellows) |
| P_set | number | Pa abs | R2 required | (P_atm, P0] | R2 | set pressure |
| P_atm | number | Pa | 101325 | > 0 | R2 | atmospheric pressure, for gauge conversions |
| overpressure | number | – | 0.10 | 0.10, 0.16 or 0.21 | R2 | allowed overpressure fraction (fluids' API520_B accepts these three) |
| valve_type | string | – | "conventional" | conventional, balanced_bellows, pilot | R2 | valve type |
| L_in_m, D_in_m, K_in, roughness_in_m | number | m, m, –, m | 0, –, 0, 4.57e-5 | ≥ 0 | R2 | inlet line: length, ID, ΣK, roughness |
| L_out_m, D_out_m, K_out, roughness_out_m | number | m, m, –, m | 0, –, 0, 4.57e-5 | ≥ 0 | R2 | discharge line |

The default roughness of 4.57e-5 m is commercial steel (Moody 1944; Crane TP-410).

R1 schema:
```yaml
type: object
required: [P_back]
properties:
  P_back: {type: number, description: 'superimposed back pressure, Pa abs'}
  Kd: {type: number, description: 'discharge coefficient; default 0.975 gas / 0.85 two-phase / 0.65 liquid'}
  Kb: {type: number, description: 'back-pressure correction, default 1.0'}
  Kc: {type: number, description: 'combination correction, default 1.0'}
  Kv: {type: number, description: 'viscosity correction, default 1.0'}
  Kw: {type: number, description: 'liquid back-pressure correction, default 1.0'}
```
R2 schema: the R1 schema plus:
```yaml
required: [P_back, P_set]
properties:
  P_set: {type: number, description: 'set pressure, Pa abs'}
  P_atm: {type: number, description: 'atmospheric pressure, Pa, default 101325'}
  overpressure: {type: number, description: 'overpressure fraction: 0.10, 0.16 or 0.21'}
  valve_type: {type: string, enum: [conventional, balanced_bellows, pilot]}
  L_in_m: {type: number}
  D_in_m: {type: number}
  K_in: {type: number}
  roughness_in_m: {type: number}
  L_out_m: {type: number}
  D_out_m: {type: number}
  K_out: {type: number}
  roughness_out_m: {type: number}
```

## Outputs
- **Port `outlet`:** `thermo.flash_ph(z, P_back, h_in, F)`.
- **Balances:** `duty_W = 0`, `power_W = 0`.
- **R1 info:**
  - `regime_code` (0 gas, 1 two-phase or saturated, 2 subcooled low, 3 subcooled high choked, 4 subcooled non-flashing);
  - `omega` (ω or ωs), `eta_c`, `critical` (0/1), `G_kg_m2s`;
  - `required_area_m2`, `required_area_mm2`, `required_area_in2`, `selected_orifice_area_in2`;
  - `Kd_used`, `P_sat_Pa` (liquid only), `v0_m3_kg`.
  - The gas regime carries R0's info plus `regime_code`.
- **R2 info:** all of R1's, plus:
  - `W_rated_kg_s`;
  - `dP_inlet_Pa`, `inlet_loss_frac` (of set gauge), `inlet_loss_ok`;
  - `dP_builtup_Pa`, `P_back_total_Pa`, `backpressure_frac` (of set gauge), `backpressure_ok`;
  - for bellows: `Kb_fig30` or `Kw_fig31`, and `area_with_backpressure_in2`.

## Tests
- **Closed-form** (pure functions; independent script `calc_relief_valve.py`, which uses its own bisection, not brentq or fluids):
  - **η_c exact:**
    - ω=0.5 → 0.515218981376155;
    - ω=1 → 0.606530659712634, which equals e^(−0.5) to 1e-15;
    - ω=5 → 0.790060291109699;
    - ω=20 → 0.893774347286082.
    - Leung's fit is within 2e-4 relative at each.
  - **TP1** (ω=5, P0=1.0e6 Pa, v0=0.02 m³/kg):
    - η_c = 0.790060291109699; **G_crit = 2498.39000876233** kg/(m²·s);
    - the subcritical formula at ηa = η_c gives the same value to 1e-12;
    - Pa/P0 = 0.8 (subcritical) gives **G = 2497.27854469590**;
    - W = 10 kg/s with Kd 0.85 and the other factors 1 gives **A = 4.70891487761794e-3 m²** (7.29883265797312 in²).
  - **ω from v9/v0 = 1.55:** 4.95.
  - **Subcooled, low** (ωs=10, ηs=0.97, η_st=0.952380952380952, P0=1e6, ρl0=600): η_c = 0.883320897206597, **G = 6947.17538436639**.
  - **Subcooled identity at ηs = 1:** η 0.848568875287966 and G 6572.98624420048 equal the saturated ω = 10 results to 1e-12.
  - **Subcooled, high** (ηs = 0.5 < η_st, Pa < Ps): G = sqrt(2·600·5e5) = **24494.8974278318**.
  - **Liquid non-flashing** (the API 520 Part I 10th ed. liquid example's arithmetic: Q = 6814 L/min, ρ = 0.9·999, P1 = 1.1·1724e3 + 101325, P2 = 0.2·1724e3 + 101325, Kd 0.65, Kw 0.97): G = 52821.2752591226, **A = 3.06594883829264e-3 m²**.
  - **R2 inlet loss** (W_req 10, A_req 0.004, A_sel 0.0045 so W_rated 11.25; ρ 50, μ 1.2e-5, D 0.1023, L 2.0, ε 4.57e-5, K 0.5):
    - v = 27.3741958001557, Re = 11668250.9598164, f = 0.0163346296356747;
    - **ΔP_in = 15349.3833307729 Pa**, so frac = 0.0170800159465578 of (1e6 − 101325).
  - Tolerances: 1e-10 relative, except 1e-9 on the brentq-based η and Colebrook-based ΔP.
- **Identity:** R1 gas equals R0. R2 with zero-length lines equals R1.
- **Unit level:**
  - A two-phase inlet built with `thermo.flash_pvf` at vapour fraction 0.2 (propane/n-butane, at ~2 MPa): ω equals 9(v9/v0 − 1) recomputed in the test from `thermo.flash_ps` and the stream phases.
  - The area equals eq. 5 recomputed from the reported G.
  - A subcooled propane liquid (T0 = 300 K, P0 = 2× bubble P) gives regime_code 3 or 4 according to P_back.
- **Refusals:** one test per refusal row, with `match=`.
- **V1 candidates:**
  1. API 520 Part I, 10th ed. (2020), liquid sizing example (fluids cites it as "Example 5"). Printed inputs: 6814 L/min, SG 0.9, set 1724 kPag, 10 % overpressure, back pressure up to 20 %, balanced bellows Kw = 0.97, first-pass Kv = 1. The printed result is **3066 mm²**, which the fluids docstring states it matches. The implementer must confirm it against the standard. At unit level this needs a feed whose thermo density at relieving conditions is 899.1 kg/m³; choose a component and T, and record the density mismatch in `assessed`.
  2. API 520 Part I Annex C two-phase (omega) and subcooled examples, and the worked examples in Leung (1996) CEP.
  - V1 gap if neither is accessible. Search places: API 520 Part I Annex C examples; CCPS "Guidelines for Pressure Relief and Effluent Handling Systems" (2nd ed., 2017) worked examples; Darby, Meiller & Stockton, "Select the best model for two-phase relief sizing", CEP 97(5), 2001.
  - Never use fluids outputs as expected values.

## Steps (each about 40 minutes, each ending in a push)
1. **Pure omega functions:** `omega_two_phase`, `eta_c`, `G_two_phase`, `G_subcooled`, `area_m2`. All closed-form tests above. Push and open the PR.
2. **The `ReliefValveR1` adapter:** regime classification, v0/v9/ρ9 from flashes, gas delegation, outlet, info, refusals, `example_case` (a two-phase propane/n-butane basis). The R0 identity test and the unit-level tests. Push.
3. **The `ReliefValveR2` adapter:** rated capacity, inlet loss, built-up back-pressure fixed point, limits, bellows Kb/Kw re-sizing, refusals, `example_case`. The R2→R1 identity and the R2 closed-form inlet-loss test. Push.
4. **Catalogue `levels.R1` and `levels.R2`** (adapters `ngdesign.units.flow.relief_valve_r1:ReliefValveR1` and `...relief_valve_r2:ReliefValveR2`, provisional, the schemas above, notes, validation ids). `cases/relief_valve.yaml` or the gap. Regenerate docs and `--audit` (separately), run the gates, push and comment.

## Review checklist (for the orchestrator)
- The η_c equation is exactly as eq. 2, and ω uses an **isentropic** flash to 0.9·P0.
- The subcooled branch boundaries: η_st = 2ωs/(1 + 2ωs); the high-subcooling choke is at Ps; the non-flashing case uses Pa.
- The Kd default depends on regime and is reported (`Kd_used`).
- The gas path delegates to R0 (no second gas sizing implementation).
- R2 uses the **rated** capacity (A_sel/A_req scaling) for the line losses.
- fluids `API520_B`/`API520_W` get **absolute** pressures; the 50 % refusal is typed.
- The back-pressure fixed point has a cap and a typed error.
- Both identity tests are present.
- No fluids docstring number appears as a V1 expected value.
