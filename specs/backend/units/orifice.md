# orifice R1: ISO 5167-2 orifice rating and sizing (Reader-Harris/Gallagher C, expansibility, permanent loss)

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from `planned` to `provisional`. R1 is the row's end state.
- **Depends on:** U-R2 conventions, U-01d. No other unit spec.
- **Wave/order:** parallel-safe. It shares no owned file.
- **Branch:** `u-lv/orifice` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/orifice_r1.py` (new)
  - `tests/units/flow/test_orifice_r1.py` (new)
  - `data/validation_units/flow/cases/orifice.yaml` (new)
  - in `data/unit_models/flow.yaml`, row `orifice`: the `levels.R1` entry, plus the `notes` line for a V1 gap
- **Read-only imports (verified, fluids 1.3.1):**
  - `fluids.flow_meter.C_Reader_Harris_Gallagher(D, Do, rho, mu, m, taps='corner') -> float`. `taps` ∈ {'corner', 'flange', 'D', 'D/2', 'D and D/2'}; 'D' and 'D/2' both mean D and D/2 taps.
    - It contains two terms that are not in ISO 5167-2:2003 (a `max(log10(3700/Re_D), 0)` factor and a `max(22.7 − 0.0047·Re_D, (1e6/Re_D)^0.3)` term, from Reader-Harris 2015). Both reduce to the ISO equation for Re_D > 4830, which the ISO validity limit Re_D ≥ 5000 guarantees, so inside validity this call **is** ISO 5167-2 eq. (4).
  - `fluids.flow_meter.orifice_expansibility(D, Do, P1, P2, k) -> float`, the ISO 5167-2:2003 eq. (5).
  - `ngdesign.units.flow.orifice.Orifice`, `OrificeSpecError`, `permanent_loss_ratio(beta, C)`, `MIN_PRESSURE_RATIO` (= 0.75) and `R_IDEAL` (R0, read-only; the permanent loss is reused, not re-derived).
  - `scipy.optimize.brentq`
  - `Thermo.flash_ph`, `Thermo.phase_props`
- **Current state (R0):** `ngdesign.units.flow.orifice:Orifice`, ports `inlet -> outlet`.
  - Params `bore_m`, `beta` and `Cd`, all required; the pipe D is implied as bore/β.
  - dP from `ṁ = Cd·E·A·Y·sqrt(2ρΔP)`, with E = 1/sqrt(1 − β⁴), the gas Y fixed point (1e-10 relative, 50 iterations), and a refusal when P2/P1 < 0.75.
  - The outlet is at P1 − the permanent loss (ISO 5167-2 §5.4).
  - info: `dP_Pa`, `permanent_loss_Pa`, `velocity_approach` (E), `expansibility` (Y).

## Method
### Equations
ISO 5167-1:2003 and ISO 5167-2:2003. The implementer confirms each clause number against the standard in the module docstring.
1. **Mass flow** (ISO 5167-2 eq. 1): `qm = C/sqrt(1 − β⁴) · ε · (π/4)·d² · sqrt(2·Δp·ρ1)`, so `Δp = (qm/(C·E·A·ε))² / (2ρ1)`, with β = d/D.
2. **Discharge coefficient**, Reader-Harris/Gallagher (eq. 4), with `Re_D = 4·qm/(π·D·μ1)`, `A = (19000·β/Re_D)^0.8` and `M2' = 2·L2'/(1 − β)`:
   `C = 0.5961 + 0.0261β² − 0.216β⁸ + 0.000521(10⁶β/Re_D)^0.7 + (0.0188 + 0.0063A)·β^3.5·(10⁶/Re_D)^0.3 + (0.043 + 0.080e^(−10L1) − 0.123e^(−7L1))(1 − 0.11A)·β⁴/(1 − β⁴) − 0.031(M2' − 0.8·M2'^1.1)·β^1.3`.
   - For D < 71.12 mm, add `0.011(0.75 − β)(2.8 − D/25.4 mm)`.
   - Tap positions: corner L1 = L2' = 0; D and D/2: L1 = 1, L2' = 0.47; flange: L1 = L2' = 25.4 mm/D.
3. **Expansibility** (eq. 5): `ε = 1 − (0.351 + 0.256β⁴ + 0.93β⁸)·[1 − (p2/p1)^(1/κ)]`, valid for p2/p1 ≥ 0.75. For a liquid, ε = 1. κ = cp/(cp − R) from the inlet vapour, the same ideal-gas relation as R0.
4. **Permanent pressure loss** (§5.4): `Δϖ/Δp = (sqrt(1 − β⁴(1 − C²)) − Cβ²)/(sqrt(1 − β⁴(1 − C²)) + Cβ²)`. Call R0's `permanent_loss_ratio(beta, C)`.
5. **Validity** (ISO 5167-2 §5.3.1; confirm against the standard):
   - d ≥ 12.5 mm; 50 mm ≤ D ≤ 1000 mm; 0.1 ≤ β ≤ 0.75;
   - corner and D–D/2 taps: Re_D ≥ 5000 for β ≤ 0.56, and Re_D ≥ 16000β² for β > 0.56;
   - flange taps: Re_D ≥ 5000 and Re_D ≥ 170β²·D (D in mm).

### Algorithm
The adapter is `OrificeR1`. The pure function `orifice_dp(qm, D, d, rho, mu, P1, kappa_or_None, taps, C_specified=None) -> dict(C, epsilon, Re_D, dP, permanent_loss)` is unit-tested. Inside it:
1. If `C_specified` is given, C is that value. Otherwise `C = C_Reader_Harris_Gallagher(D, d, rho, mu, qm, taps)`; it does not depend on Δp, so no iteration is needed for C.
2. ε = 1 and Δp from eq. 1.
3. **Gas:** fixed point `ε = orifice_expansibility(D, d, P1, P1 − Δp, κ)` and `Δp = (qm/(C·E·A·ε))²/(2ρ)`, until |ΔΔp| < 1e-12·Δp, with a 100-iteration cap raising `OrificeR1Error`. Before each ε evaluation, refuse if (P1 − Δp)/P1 < 0.75 (validity, as R0).
4. **Liquid:** refuse if Δp ≥ P1.
5. `permanent_loss = permanent_loss_ratio(β, C)·Δp`.

**Adapter:**
1. Phase class as R0: gas if vf > 0.999 (vapour properties); otherwise the dominant dense phase. Refuse two-phase (0.001 < vf < 0.999): "ISO 5167 requires single-phase flow".
2. μ is the phase viscosity, else `mu_Pa_s`, else refuse.
3. **Mode:**
   - **Rating** (`bore_m` given): `orifice_dp`.
   - **Sizing** (`dP_design_Pa` given instead): solve d with `brentq` on `d ∈ [max(0.1·D, 0.0125), 0.75·D]` for `orifice_dp(d).dP − dP_design = 0` (Δp decreases monotonically with d), with xtol 1e-12 m, rtol 4·DBL_EPSILON and maxiter 100. If the target is outside `[dP(d_hi), dP(d_lo)]`, refuse "no bore within the ISO 5167-2 range gives dP_design …".
4. Validity check (eq. 5) on the final d and Re_D; refuse outside.
5. Outlet: `thermo.flash_ph(z, P1 − permanent_loss, h_in, F)`.

### Reduction to the lower level
With `C_specified = Cd`, `D_m = bore_m/beta` and `taps` irrelevant, R1 rating equals R0 for the same `bore_m`. Use the R0 example case: liquid condensate, bore 0.05 m, β = 0.5, Cd 0.61, so D = 0.1 m.
- The validity check still applies: D = 100 mm, d = 50 mm and β = 0.5 are all valid, and Re_D must also be checked; choose the example flow so it is valid.
- Assertions: `dP_Pa` and `permanent_loss_Pa` equal R0's to 1e-12 relative for a liquid (no iteration), and to 1e-9 for a gas (R0 converges to 1e-10). The outlet state is identical.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| neither or both of `bore_m`/`dP_design_Pa` | `OrificeR1Error(OrificeSpecError)`, new | "exactly one of bore_m / dP_design_Pa" |
| `D_m` missing or ≤ 0 | `OrificeR1Error` | "D_m" |
| `taps` not in {corner, flange, D-D/2} | `OrificeR1Error` | "taps" |
| `C_specified` outside (0, 1) | `OrificeR1Error` | "C_specified" |
| ISO validity (d, D, β, Re_D) violated | `OrificeR1Error` | "outside ISO 5167-2 validity" plus the violated quantity |
| p2/p1 < 0.75 (gas) | `OrificeR1Error` | "P2/P1" |
| liquid Δp ≥ P1 | `OrificeR1Error` | "exceeds the inlet pressure" |
| two-phase inlet | `OrificeR1Error` | "single-phase" |
| no viscosity | `OrificeR1Error` | "mu_Pa_s" |
| expansibility fixed point at the cap | `OrificeR1Error` | "did not converge" |
| sizing target unreachable | `OrificeR1Error` | "no bore" |
| brentq failure | `OrificeR1Error` | "sizing did not converge" |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| D_m | number | m | required | 0.05..1.0 | pipe internal diameter |
| bore_m | number | m | rating: required | ≥ 0.0125, β in [0.1, 0.75] | orifice bore |
| dP_design_Pa | number | Pa | sizing: required | > 0 | differential at the stream flow |
| taps | string | – | "flange" | corner, flange, D-D/2 | tap arrangement |
| C_specified | number | – | none (RHG) | (0, 1) | fixed C (R0 equivalence) |
| mu_Pa_s | number | Pa·s | none | > 0 | viscosity override |

```yaml
type: object
required: [D_m]
properties:
  D_m: {type: number, description: 'pipe internal diameter, m (ISO 5167-2: 0.05 to 1.0)'}
  bore_m: {type: number, description: 'rating mode: orifice bore, m'}
  dP_design_Pa: {type: number, description: 'sizing mode: differential pressure at the stream flow, Pa'}
  taps: {type: string, enum: [corner, flange, D-D/2], description: 'tap arrangement, default flange'}
  C_specified: {type: number, description: 'fixed discharge coefficient instead of Reader-Harris/Gallagher'}
  mu_Pa_s: {type: number, description: 'viscosity override, Pa.s'}
```

## Outputs
- **Port `outlet`:** `flash_ph(z, P1 − permanent_loss, h_in, F)`.
- **Balances:** `duty_W = 0`, `power_W = 0`.
- **info:**
  - `C`, `expansibility`, `Re_D`, `beta`, `bore_m`;
  - `dP_Pa` (tap differential), `permanent_loss_Pa`, `velocity_approach`;
  - `sizing` (0/1).

## Tests
- **Closed-form** (independent script `calc_orifice.py`, with its own ISO eq. (4) implementation; it agrees with fluids to the last digit inside validity):
  - **O1** (liquid; D = 0.10226, d = 0.05, flange taps, qm = 10 kg/s, ρ = 998, μ = 1e-3, P1 = 5e5):
    - Re_D = 124510.027844237; **C = 0.605255904072185**; ε = 1;
    - **Δp = 33445.8129428092 Pa**; permanent loss = 24852.9608421957 Pa.
  - **O2** (gas; D = 0.10226, d = 0.06, corner taps, qm = 1.5, ρ = 40, μ = 1.2e-5, P1 = 5e6, κ = 1.3):
    - Re_D = 1556375.34805296; **C = 0.604878186749537**;
    - ε = 0.999485073056371; **Δp = 8484.63326807909 Pa**; permanent loss = 5464.24065361060 Pa.
  - **O3** (small pipe; D = 0.05 m, which brings in the D < 71.12 mm term; d = 0.025, D-D/2 taps, liquid qm = 2.0):
    - Re_D = 50929.5817894065; **C = 0.610337411029475**; **Δp = 20931.0469127572 Pa**; permanent loss = 15292.2601494554 Pa.
  - **S1** (sizing; O1's fluid and flow, target Δp = 25000 Pa, flange taps): **bore = 0.0534567804546456 m** (β = 0.522753573779049).
  - Tolerances: 1e-10 relative (S1 at 1e-9 for the root solve).
- **Identity:** R1 with `C_specified` equals R0 (above).
- **Unit level:** on a liquid condensate inlet, the reported `C` equals `C_Reader_Harris_Gallagher` called by the test with the reported D, d, Re-implied flow, ρ and μ, and `dP_Pa` satisfies eq. 1 recomputed in the test to 1e-12.
- **Refusals:** one per refusal row, with `match=`.
- **V1 candidates:** ISO 5167 has no normative worked examples. Candidates:
  - API MPMS Chapter 14.3 Part 4 / AGA Report No. 3 Part 4 (implementation procedure with example calculations, natural gas, flange taps);
  - Miller, *Flow Measurement Engineering Handbook* (3rd ed., 1996) ch. 9 examples;
  - Reader-Harris, *Orifice Plates and Venturi Tubes* (Springer, 2015) worked examples.
  - The implementer transcribes the printed inputs and results only. Otherwise a V1 gap is recorded in the row notes, naming these.

## Steps (each about 40 minutes, each ending in a push)
1. **The pure `orifice_dp`** (C via fluids or `C_specified`, liquid and gas ε fixed point, permanent loss via R0) and the validity check. Closed-form tests O1, O2, O3. Push and open the PR.
2. **The `OrificeR1` adapter:** rating and sizing (brentq), phase class, viscosity, refusals, outlet, info, `example_case`. S1, the R0 identity, the unit-level and refusal tests. Push.
3. **Catalogue `levels.R1`** (adapter `ngdesign.units.flow.orifice_r1:OrificeR1`, provisional, the schema, note "ISO 5167-2 RHG C, expansibility, permanent loss; rating and sizing", validation ids). `cases/orifice.yaml` or the gap. Docs and `--audit`, gates, push and comment.

## Review checklist (for the orchestrator)
- C comes from fluids RHG (or `C_specified`), and the docstring states the inside-validity equivalence to ISO eq. (4).
- The ISO validity limits are enforced with typed refusals.
- Permanent loss reuses R0's `permanent_loss_ratio`.
- Re_D uses the **pipe** diameter: Re_D = 4qm/(πDμ).
- The gas fixed point has a cap and refuses p2/p1 < 0.75 before each ε.
- Sizing is a capped brentq on the same forward function as rating (no second model).
- The R0 identity is exact for a liquid.
