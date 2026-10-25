# ejector R1: 1-D constant-pressure mixing model (nozzle, mixing, diffuser efficiencies) giving the achievable discharge pressure

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from `planned` to `provisional`. R1 is the row's end state.
- **Depends on:** U-R2 conventions, U-01d. No other unit spec.
- **Wave/order:** parallel-safe. It shares no owned file.
- **Branch:** `u-lv/ejector` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/ejector_r1.py` (new)
  - `tests/units/flow/test_ejector_r1.py` (new)
  - `data/validation_units/flow/cases/ejector.yaml` (new)
  - in `data/unit_models/flow.yaml`, row `ejector`: the `levels.R1` entry, plus the `notes` line for a V1 gap
- **Read-only imports (verified):**
  - `ngdesign.units.flow.ejector.Ejector`, `EjectorSpecError` (R0, read-only; the identity test calls R0);
  - `Thermo.flash_ps(z, P, S, F)`, `Thermo.flash_ph(z, P, H, F)`;
  - `StreamState.mass_flow`, `.molar_flow`, `.enthalpy`, `.entropy`, `.composition`;
  - `scipy.optimize.brentq`.
- **Current state (R0):** `ngdesign.units.flow.ejector:Ejector`, ports `motive_in`, `suction_in -> outlet` (U-01c names).
  - Params `P_out` (required) and `entrainment` (kg suction per kg motive, required).
  - Adiabatic mixing: `h_mix = (n_m·h_m + n_s·h_s)/(n_m + n_s)`, with the outlet a PH flash at `P_out`.
  - It reports the achieved entrainment against the spec.
  - It does not compute what discharge pressure the streams can actually reach.

## Method
### Equations
The constant-pressure mixing ejector model of Keenan, Neumann & Lustwerk, "An investigation of ejector design by analysis and experiment", J. Appl. Mech. 17:299–309 (1950), with the component-efficiency form of Huang, Chang, Wang & Petrenko, "A 1-D analysis of ejector performance", Int. J. Refrig. 22(5):354–364 (1999). ESDU 86030 is cited for context only; no ESDU data or equations are copied.

Assumptions, stated in the docstring:
- steady, adiabatic, 1-D;
- the motive expands to the suction pressure Ps, and mixing happens at constant Ps;
- the suction stream enters the mixing section at negligible velocity;
- the outlet velocity is negligible (stagnation state at discharge);
- the efficiencies are constants supplied by the user.

Symbols: ṁ in kg/s; n in mol/s; h in J/mol; MW in kg/mol, as `mass_flow/molar_flow`.
1. **Motive nozzle:** `h_is = h(Ps, s_p)` from an isentropic flash. `Δh_n = η_n·(h_p − h_is)` in J/mol. `u_p = sqrt(2·Δh_n/MW_p)` in m/s.
2. **Mixing momentum:** `(ṁ_p + ṁ_s)·u_m = φ_m·ṁ_p·u_p`, where φ_m is the mixing-section momentum coefficient (Huang 1999).
3. **Mixing energy:** the stagnation enthalpy is conserved, `h_0 = (n_p·h_p + n_s·h_s)/(n_p + n_s)`, which is exactly R0's `h_mix`. The static enthalpy after mixing is `h_m = h_0 − MW_mix·u_m²/2`, with `MW_mix = (ṁ_p + ṁ_s)/(n_p + n_s)`.
4. **Mixed static state:** `s_m = s(Ps, h_m)` from a PH flash of z_mix.
5. **Diffuser:** the isentropic static-enthalpy rise is `η_d` times the kinetic energy: `h(P_out, s_m) = h_m + η_d·MW_mix·u_m²/2`, which is solved for P_out.
6. **Outlet** at stagnation: `flash_ph(z_mix, P_out, h_0, n_p + n_s)`. Energy closes exactly: `Σ n·h_in = (n_p + n_s)·h_0`.

### Algorithm
Write a pure core, `ejector_core(np, ns, MWp, MWs, hp, sp, hs, Pp, Ps, eta_n, phi_m, eta_d, h_at_PS_motive, h_at_PS_mix, s_at_PH_mix, P_hi) -> dict`, where the callables are injected:
- the adapter passes thermo-backed lambdas, `lambda P, s: thermo.flash_ps(z, P, s, F).enthalpy` and similar;
- the closed-form test passes calorically perfect ideal-gas lambdas.

Steps:
1. Validate. Pp > Ps (else refuse "motive pressure … must exceed suction pressure …"). Efficiencies in (0, 1].
2. Eqs. 1–4. Refuse if `Δh_n ≤ 0`. No check compares `h_m` with the motive `h_is`: a cold suction stream legitimately makes the mix's static enthalpy lower.
3. Eq. 5: `g(P) = h_at_PS_mix(P, s_m) − (h_m + η_d·MW_mix·u_m²/2)`.
   - `g(Ps) = −η_d·MW_mix·u_m²/2 < 0`.
   - The upper bracket is `P_hi = Pp`. If `g(Pp) < 0`, the diffuser would compress above the motive pressure; refuse "computed discharge exceeds the motive pressure; check efficiencies". A real ejector cannot do this.
   - `brentq(g, Ps, Pp, xtol=1e-9·Ps, rtol=4·DBL_EPSILON, maxiter=100)`. Raise `EjectorR1Error` on failure.
4. Outlet per eq. 6.
5. If `P_out_required` is given, report `meets_discharge = 1.0 if P_out ≥ P_out_required else 0.0` and `discharge_margin_Pa = P_out − P_out_required`. The outlet state is still at the **computed** P_out, because R1 is a rating model.

**Adapter** `EjectorR1`: builds z_mix (molar average, as R0), MWs from the streams, the callables, then runs the core.

### Reduction to the lower level
For any R1 solve, R0 run with `P_out = info["P_out_Pa"]` and `entrainment = ṁ_s/ṁ_p` gives the identical outlet state (same h_0, same flash). Assert T and P exactly and the enthalpy to 1e-12. h_0 equals R0's `h_mix` by construction.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| Pp ≤ Ps | `EjectorR1Error(EjectorSpecError)`, new | "motive pressure" |
| any of eta_nozzle, phi_mix, eta_diffuser outside (0, 1] | `EjectorR1Error` | the name |
| Δh_n ≤ 0 | `EjectorR1Error` | "no nozzle enthalpy drop" |
| `g(Pp) < 0` | `EjectorR1Error` | "exceeds the motive pressure" |
| brentq failure | `EjectorR1Error` | "did not converge" |
| zero flow on either inlet | `EjectorR1Error` | "molar_flow" |
| `P_out_required` ≤ 0 | `EjectorR1Error` | "P_out_required" |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| eta_nozzle | number | – | 0.95 | (0, 1] | motive nozzle isentropic efficiency (Huang 1999 used 0.95) |
| phi_mix | number | – | 0.85 | (0, 1] | mixing momentum coefficient (Huang 1999 range about 0.80–0.84; supply a calibrated value) |
| eta_diffuser | number | – | 0.85 | (0, 1] | diffuser isentropic efficiency |
| P_out_required | number | Pa | none | > 0 | optional: report whether the computed discharge meets it |

```yaml
type: object
properties:
  eta_nozzle: {type: number, description: 'motive nozzle isentropic efficiency, default 0.95'}
  phi_mix: {type: number, description: 'mixing momentum coefficient, default 0.85'}
  eta_diffuser: {type: number, description: 'diffuser isentropic efficiency, default 0.85'}
  P_out_required: {type: number, description: 'optional required discharge pressure, Pa'}
```

## Outputs
- **Port `outlet`:** `flash_ph(z_mix, P_out, h_0, n_p + n_s)`.
- **Balances:** `duty_W = 0`, `power_W = 0`.
- **info:**
  - `P_out_Pa`, `compression_ratio` (P_out/Ps);
  - `u_motive_m_s`, `u_mix_m_s`;
  - `entrainment_kg_kg` (ṁ_s/ṁ_p);
  - `h_static_mix_J_mol`;
  - `meets_discharge` and `discharge_margin_Pa` when `P_out_required` is given.

## Tests
- **Closed-form** (independent script `calc_ejector.py`, per-kg ideal gas). The core is injected with calorically perfect air:
  - M = 0.0289647 kg/mol, κ = 1.4, cp,molar = κ/(κ − 1)·R;
  - `h(T) = cp·T`, `s(T, P) = cp·ln T − R·ln P`, so `h_at_PS(P, s) = cp·exp((s + R·ln P)/cp)` and `s_at_PH(P, h) = cp·ln(h/cp) − R·ln P`.
  - Inputs: motive Pp = 6.0e5 Pa, Tp = 400 K, ṁ_p = 1.0 kg/s; suction Ps = 1.0e5 Pa, Ts = 300 K, ṁ_s = 0.5 kg/s; η_n = 0.95, φ_m = 0.85, η_d = 0.85.
  - Expected:
    - T_is = 239.734789884704 K; u_p = 553.111930840640 m/s; u_m = 313.430094143029 m/s;
    - T_m = 317.776873958717 K; **P_out = 153749.137554408 Pa**; T_out = 366.666666666667 K.
  - With all efficiencies 1: **P_out = 212970.469869893 Pa**.
  - Tolerance 1e-9 relative on P_out (brentq xtol 1e-9·Ps) and 1e-12 on the velocities.
- **Identity:** R1 to R0, as above, on R0's own `example_case` (steam motive at 500 K / 1 MPa, suction at 300 K / 2 kPa).
- **Monotonicity:** a higher φ_m gives a higher P_out (it must hold on the example).
- **Refusals:** one per refusal row, with `match=`.
- **V1 candidates:** no open source prints inputs and results for a full steam-ejector rating that the thermo can reproduce exactly. Candidates:
  - Huang et al. (1999) Table 2/3 (R141b test data with measured entrainment and critical back pressure; needs R141b in the component set, otherwise a gap);
  - Power, *Steam Jet Ejectors for the Process Industries* (McGraw-Hill, 1994), worked design examples;
  - Perry's 9th ed. §10, ejector examples.
  - Record a V1 gap in the row notes naming these if not reproducible. ESDU 86030 is cited only (proprietary); none of its numbers.

## Steps (each about 40 minutes, each ending in a push)
1. **The pure `ejector_core`** with injected callables. The ideal-gas closed-form test (both efficiency sets) and the monotonicity test. Push and open the PR.
2. **The `EjectorR1` adapter:** thermo callables, validation, outlet, info, `P_out_required` reporting, refusals, `example_case` (R0's basis without `P_out`/`entrainment`). The R0 identity test and the refusal tests. Push.
3. **Catalogue `levels.R1`** (adapter `ngdesign.units.flow.ejector_r1:EjectorR1`, provisional, the schema, note "Keenan constant-pressure mixing with Huang efficiencies: achievable discharge pressure", validation ids). `cases/ejector.yaml` or the gap. Docs and `--audit`, gates, push and comment.

## Review checklist (for the orchestrator)
- The outlet uses the **stagnation** enthalpy h_0 (= R0's h_mix), so V0 is exact.
- The diffuser equation is applied from the **static** mixed state (P_s, s_m).
- J/mol ↔ J/kg conversions use MW = mass_flow/molar_flow, in kg/mol.
- The brentq bracket is [Ps, Pp], with a typed refusal when it is not bracketed.
- No ESDU numbers appear.
- The identity is exact.
- The defaults are listed in the params table and catalogue schema (no hidden constants).
