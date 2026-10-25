# hydrate_check R1: Katz gas-gravity hydrate temperature (Towler-Mokhatab fit), with the method selectable

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/hydrate_check` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/hydrate_check_r1.py` (new): `HydrateCheckR1`, `HydrateCheckR1SpecError`, `towler_mokhatab_T_K(P_Pa, sg)`
  - `tests/units/separation/test_hydrate_check_r1.py` (new)
  - `data/validation_units/separation/cases/hydrate_check.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `hydrate_check`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separation.hydrate_check`: `HydrateCheck` (R0), `HydrateCheckSpecError`, `MW_AIR_G_MOL`, `_required_dose`, `_inhibitor_in`, `_inhibitor_mass_fraction`. Private names are imported read-only, and only these four. If you prefer not to import private names, call `HydrateCheck().solve` and recompute only the hydrate T and the dose.
  - `ngdesign.sizing.hydrates.hammerschmidt_formation(P_Pa, gas_specific_gravity) -> {"T_hydrate_K"}` and `nielsen_bucklin_suppression(...)`
  - `ngdesign.units.separation._util.stream_molar_mass`
- **Current state:**
  - R0 does an adiabatic PH mix of the gas and inhibitor inlets.
  - It reports `hydrate_T_K` from `hammerschmidt_formation` at the mixed P with the gas-inlet SG (MW/28.9625), `suppression_K` from Nielsen-Bucklin on the aqueous phase, and the required dose for `T_operating_K` by bisection.
  - V1 is `V1-hydrate-gpsa-20-10`, the dose anchor.
- **Not available (checked):** no van der Waals-Platteeuw hydrate model is exposed by any `ngdesign.thermo` package (grep: none). The vdWP route in the row note **requires a thermo contract addition and is out of scope**. Record that in the R1 note.

## Method
### Equations
- **K1 Katz gas-gravity method** (Katz, Trans. AIME 160:140, 1945; GPSA Engineering Data Book, Sect. 20, gravity chart), represented by the **Towler & Mokhatab (2005)** fit (Hydrocarbon Processing 84(4):61):
  - `T[°F] = 13.47·ln P + 34.27·ln γ − 1.675·(ln P)(ln γ) − 20.35`, with P in psia and γ the gas specific gravity;
  - SI conversion: `P_psia = P_Pa/6894.757293168` (the constant `_PSIA_PER_PA` in `sizing/hydrates.py`) and `T_K = (T_F + 459.67)/1.8`.
  - **Constant check (mandatory):** transcribe the four coefficients and the paper's stated validity ranges in γ, P and T **from the paper**, or from a reproduction that cites it. List them in the PR body. If the transcription differs from the values above, use the paper's values and **recompute CF1–CF3** with the independent script.
- **K2 Hammerschmidt** (R0): `hammerschmidt_formation`, called and never re-derived.
- **K3 Validity:** outside the paper's stated range of γ or P, refuse with a typed error naming the range. Never extrapolate silently.
- **K4 Dose:** the required suppression is `ΔT = T_hyd − T_operating`. The dose comes from R0's `_required_dose` (Nielsen-Bucklin bisection) with R1's `T_hyd`; the dose method is unchanged from R0.

### Algorithm
1. `method = params.get("hydrate_method", "towler_mokhatab")`, either `"towler_mokhatab"` or `"hammerschmidt"`.
2. `r0 = HydrateCheck().solve(inlets, r0_params, thermo)`, where `r0_params` is the params minus `hydrate_method`. Keep the outlet and the duty: **R1 changes no stream**.
3. For `"hammerschmidt"`: return r0 unchanged, with `info["hydrate_method_index"] = 0.0`.
4. For `"towler_mokhatab"`:
   - the mixed P is the outlet P; SG is computed exactly as R0 does (gas-inlet MW / `MW_AIR_G_MOL`);
   - `T_hyd = towler_mokhatab_T_K(P, SG)`, range-checked (K3);
   - `info["hydrate_T_K"] = T_hyd`, `info["hydrate_T_hammerschmidt_K"]` = R0's value, and `info["hydrate_method_index"] = 1.0`;
   - if `T_operating_K` is given, recompute `required_inhibitor_mass_fraction` and `required_inhibitor_rate_kg_s` with R0's `_required_dose(outlet, aqueous, inhibitor_cid, T_hyd − T_operating)`. `suppression_K` is unchanged, because it does not depend on the hydrate T.

### Reduction to the lower level
`hydrate_method="hammerschmidt"` gives the outlet, duty and every R0 `info` key equal (`==`) to R0's.

### Refusals (`HydrateCheckR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `hydrate_method` not in {towler_mokhatab, hammerschmidt} | `hydrate_method` |
| SG or P outside the Towler-Mokhatab range (as transcribed) | `Towler-Mokhatab range` |

R0's refusals propagate.

## Params
```yaml
type: object
properties:
  P: {type: number, description: 'mixed outlet pressure, Pa abs; default min inlet P (R0)'}
  T_operating_K: {type: number, description: 'target operating temperature, K; drives the dose (R0)'}
  hydrate_method: {type: string, enum: [towler_mokhatab, hammerschmidt], description: 'hydrate-temperature correlation; default towler_mokhatab (Katz gas-gravity fit)'}
```

## Outputs
- **Port:** `outlet`, R0's.
- **`info`:** R0's keys; `hydrate_T_K` per the chosen method; `hydrate_T_hammerschmidt_K`; `hydrate_method_index` (0 = Hammerschmidt, 1 = Towler-Mokhatab).

## Tests
Numbers come from `scratchpad/unit-specs/calc_hydrate_check.py` (math only).
- **CF1–CF3**, through `towler_mokhatab_T_K`, rtol 1e-9:
  | P (Pa) | SG | T (K) |
  |---|---|---|
  | 7.0e6 | 0.65 | 290.446605 |
  | 3.0e6 | 0.60 | 282.69495 |
  | 10.0e6 | 0.80 | 295.805364 |

  These assume the coefficients above, so recompute them if the paper's transcription differs.
- **Physical sanity**, which the review relies on: CF1 sits within about 1 K of the Katz chart's reading near 1000 psia for SG 0.65 (about 62–63 °F, i.e. 290 K). Assert 285 < T < 295 K as a coarse guard.
- **Identity:** `hydrate_method="hammerschmidt"` on the R0 example feeds gives an R0-equal result.
- **Dose consistency:** on the R0 example feeds with `T_operating_K = T_hyd,TM − 10`, assert that `nielsen_bucklin_suppression(info.required_inhibitor_mass_fraction, MW_MeOH)` = 10 K to 1e-6 K.
- **Refusals:** an unknown method, and SG out of range (for example SG = 1.5).
- **V1 candidates:**
  - Towler & Mokhatab (2005) print a comparison with experimental hydrate data. A printed experimental point (gas gravity, P, measured T) is a V1 case only if the gas composition is printed too, because the unit computes SG from composition. Otherwise use the point through a single-component gas (C1, SG 0.5539) only if the paper's range admits it.
  - Sloan & Koh, *Clathrate Hydrates of Natural Gases*, 3rd ed., Ch. 4, gas-gravity examples. These are chart readings, i.e. figure-based, so they are not V1 unless a numeric answer is printed.
  - GPSA Sect. 20, the gravity-chart example: chart-based, so not V1.
  - Likely outcome: a V1 gap naming these.

## Steps
1. `towler_mokhatab_T_K` with the transcribed constants and range, plus CF1–CF3 and the sanity test. Push, then open the PR.
2. The `HydrateCheckR1` adapter, with the identity, dose and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.hydrate_check_r1:HydrateCheckR1`; the note says the vdWP route is out of scope because no thermo hydrate model exists). Regenerate the docs, then `--audit`. Push.
3. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- The coefficients and range are transcribed from the paper and listed in the PR.
- °F, psia and K conversions use the exact constants.
- The range is enforced.
- The dose goes through R0's bisection with R1's T.
- No stream changes, and the Hammerschmidt path is identical to R0.

## Note for the orchestrator (R0 constant concern, not this unit's to fix)
R0's `hammerschmidt_formation` evaluates `T[°F] = 8.9·P^0.285/(SG^0.249 − 0.28)`. At 7 MPa and SG 0.65 that is 312.89 K (103.6 °F). The Katz chart and Towler-Mokhatab give about 290 K, and the plain Hammerschmidt `8.9·P^0.285` gives 290.9 K. The SG divisor looks like a transcription defect in `ngdesign/sizing/hydrates.py`. It needs its own fix against the original source. This R1 is unaffected except for the `hydrate_T_hammerschmidt_K` comparison key.
