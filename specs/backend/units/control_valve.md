# control_valve R1: IEC 60534-2-1 sizing and rating with choked flow and an inherent Cv curve

- **Family / package:** flow, `src/ngdesign/units/flow/`
- **Levels delivered:** R1, from catalogue `planned` to `provisional`. R1 is the row's end state.
- **Depends on:** U-R2 conventions, U-01d (per-unit V1 case files). No other unit spec.
- **Wave/order:** parallel-safe. It shares no owned file with any other unit.
- **Branch:** `u-lv/control_valve` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/flow/control_valve_r1.py` (new)
  - `tests/units/flow/test_control_valve_r1.py` (new)
  - `data/validation_units/flow/cases/control_valve.yaml` (new)
  - in `data/unit_models/flow.yaml`, row `control_valve` only: the `levels.R1` entry, plus the row `notes` line if a V1 gap is recorded
- **Read-only imports (verified to exist, fluids 1.3.1):**
  - `fluids.control_valve.size_control_valve_l(rho, Psat, Pc, mu, P1, P2, Q, D1=None, D2=None, d=None, FL=0.9, Fd=1, allow_choked=True, allow_laminar=True, full_output=False) -> float | dict`. Returns metric Kv in m³/h/bar^0.5. Q is in m³/s at inlet conditions; pressures in Pa; mu in Pa·s. `full_output=True` returns a dict with keys `Kv, choked, laminar, FF, FR, FP, FLP, Rev`.
  - `fluids.control_valve.size_control_valve_g(T, MW, mu, gamma, Z, P1, P2, Q, D1=None, D2=None, d=None, FL=0.9, Fd=1, xT=0.7, allow_choked=True, allow_laminar=True, full_output=False) -> float | dict`. **Q is the volumetric flow at 273.15 K and 101325 Pa, in m³/s**, not actual flow. The `full_output` keys are `Kv, choked, laminar, Y, FR, FP, xTP, Rev`.
  - `fluids.control_valve.FF_critical_pressure_ratio_l(Psat, Pc) -> float`
  - `fluids.control_valve.control_valve_choke_P_l(Psat, Pc, FL, P1=None, P2=None, check_choking=True) -> float` returns the P2 at which liquid flow chokes.
  - `fluids.control_valve.control_valve_choke_P_g(xT, gamma, P1=None, P2=None) -> float` returns the P2 at which gas flow chokes.
  - `scipy.optimize.brentq`
  - `ngdesign.units.flow.control_valve.ControlValve`, `ControlValveSpecError` (R0, read-only; reused for refusals and the identity test)
  - `ngdesign.data.components()` for pure `pc_Pa`
  - `Thermo.flash_ph`, `Thermo.phase_props`, `Thermo.pure_psat`
- **Current state (R0):** `ngdesign.units.flow.control_valve:ControlValve`, ports `inlet -> outlet`. Params: exactly one of `P_out`/`dP`, plus optional `Fp` (default 1.0), `FL` (default 0.9) and `mu_liquid`.
  - Isenthalpic PH flash to the outlet pressure.
  - For an all-liquid inlet it reports `Cv` (US) from `ngdesign.sizing.control_valve.cv_liquid_isa` (fluids with `allow_laminar=False`, no fittings) divided by `Fp`, plus a `choked` flag.
  - Psat is the mole-fraction-weighted `thermo.pure_psat`, and Pc is the molar-average pure Pc (Kay's rule). Gas Cv is not reported.

## Method
### Equations
All from IEC 60534-2-1:2011 (= ANSI/ISA-75.01.01-2007). Clause and equation numbers are the standard's. Units: Q in m³/h, pressures in kPa, Kv in m³/h/bar^0.5, as in the standard; fluids converts from SI internally.
1. **Liquid, non-choked turbulent** (eq. 1): `Kv = Q/N1 · sqrt((ρ1/ρ0)/ΔP)`, with N1 = 0.1 (Table 1) and ρ0 = 999.10329 kg/m³ (water at 288.15 K, the constant fluids uses).
2. **Liquid pressure-ratio factor** (eq. 4): `FF = 0.96 − 0.28·sqrt(Psat/Pc)`.
3. **Liquid choked** when `ΔP ≥ FL²(P1 − FF·Psat)` (eq. 2). Then (eq. 3): `Kv = Q/(N1·FL) · sqrt((ρ1/ρ0)/(P1 − FF·Psat))`.
4. **Gas** (eqs. 8 and 10, volumetric form with N9 = 24.6 for 0 °C, 101.325 kPa):
   - `x = ΔP/P1`, `Fγ = γ/1.4` (eq. 13), `Y = 1 − x/(3·Fγ·xT)` (eq. 10);
   - choked when `x ≥ Fγ·xT`, in which case x is replaced by `Fγ·xT` and `Y = 2/3`;
   - `Kv = Q_std/(N9·P1·Y) · sqrt(M·T1·Z1/x)`.
5. **Standard volumetric gas flow** (the basis of N9): `Q_std = n_vapour · R·273.15/101325` m³/s, with R = 8.31446261815324 J/(mol·K), giving `Vm,std = 0.0224139695 m³/mol`.
6. **US Cv:** `Cv = Kv/0.865`, the same constant as `ngdesign.sizing.control_valve._KV_PER_CV` (IEC 60534-1 Annex: Kv = 0.865 Cv).
7. **Piping geometry factor** when `D1_m`, `D2_m` and `d_m` are all given: FP, FLP and xTP per clauses 7 and 8 (eqs. 15–19). fluids applies them when all three diameters are passed, so they are not re-derived here.
8. **Inherent flow characteristic** φ(l) = Kv(l)/Kv,rated, for relative travel l in (0, 1] (IEC 60534-2-4 / ISA-75.11.01):
   - linear: `φ = l`;
   - equal percentage: `φ = R^(l−1)`, with rangeability R (default 50);
   - quick opening: `φ = sqrt(l)`.

   Inverses: `l = φ`; `l = 1 + ln φ / ln R`; `l = φ²`.

### Algorithm
The adapter class is `ControlValveR1` in `control_valve_r1.py`. Its pure functions are module-level and unit-tested:
- `kv_liquid(Q_m3_s, rho, mu, Psat, Pc, P1, P2, FL, Fd, D1_m=None, D2_m=None, d_m=None) -> dict`
- `kv_gas(n_mol_s, MW, mu, gamma, Z, T, P1, P2, xT, FL, Fd, D1_m=None, D2_m=None, d_m=None) -> dict`
- `characteristic(l, kind, R) -> float`
- `characteristic_inverse(phi, kind, R) -> float`

`kv_liquid` and `kv_gas` call fluids with `full_output=True` and `allow_laminar=True`, and return `{Kv, choked, FR, FP, Y (gas only)}`.

1. **Phase class.** Liquid if `inlet.vapor_fraction ≤ 0.001`; gas if `≥ 0.999`; otherwise refuse with "two-phase flow is outside IEC 60534-2-1". This is the same 0.001 threshold as R0's `_liquid_phase`.
2. **Liquid properties** at the inlet: ρ1 is the dominant liquid phase's density, as in R0.
   - μ is the phase viscosity, else `params["mu_liquid"]`, else refuse with "liquid viscosity unavailable; pass mu_liquid".
   - Psat: for a single component, `thermo.pure_psat(cid, T1)`. For a mixture, `thermo.bubble_point(z, T=T1).P`, the true vapour pressure, which is the standard's intent for a mixture.
   - Pc: molar average of the pure `pc_Pa` (Kay's rule).
   - Q = mass_flow/ρ1.
3. **Gas properties** at the inlet vapour phase:
   - MW is `vapor.molecular_weight`; Z is `vapor.z_factor`, refused if None;
   - μ is the vapour viscosity, else `params["mu_gas"]`, else refuse;
   - `γ = cp/(cp − R)` from `thermo.phase_props(..., VAPOR).cp`, the same ideal-gas relation as R0's relief valve and orifice; refuse if γ ≤ 1;
   - Q_std from eq. 5 with n = `inlet.molar_flow`.
4. **Mode.**
   - **Sizing:** exactly one of `P_out`/`dP` is given, as in R0, and `Cv_rated` is optional. P2 is that pressure. Compute Kv. If `Cv_rated` is given, `φ = Kv/(0.865·Cv_rated)`; refuse when φ > 1 ("required Cv … exceeds Cv_rated …"); otherwise report `travel = characteristic_inverse(φ)`.
   - **Rating:** neither `P_out` nor `dP` is given; `Cv_rated` and `opening` are required. `Kv_avail = 0.865·Cv_rated·φ(opening)`.
     - Pipe diameters are refused in rating mode at R1 ("piping geometry factors are supported in sizing mode only").
     - P2 at choke: `control_valve_choke_P_l(Psat, Pc, FL, P1=P1)` for a liquid, `control_valve_choke_P_g(xT, γ, P1=P1)` for a gas. Then `Kv_choke = Kv(P2_choke·(1 − 1e-12))`.
     - If `Kv_avail < Kv_choke·(1 − 1e-9)`, refuse with `ChokedCapacityError`: "flow … exceeds the choked capacity of the valve at opening …".
     - Otherwise solve `g(P2) = Kv(P2) − Kv_avail = 0` with `brentq` on `[P2_choke, P1·(1 − 1e-9)]`, using `xtol = 1e-9·P1`, `rtol = 4·DBL_EPSILON` and `maxiter = 100`. On a `RuntimeError` or `ValueError` from brentq, raise `ControlValveRatingError` naming P1, Kv_avail and the bracket.
     - `Kv(P2)` increases monotonically with P2 above the choke point: eqs. 1 and 8 have ΔP or x in the denominator.
5. **Outlet:** `thermo.flash_ph(z, P2, h_in, F)`, as in R0. `duty_W = 0`, `power_W = 0`.
6. **Info:** see Outputs.

### Reduction to the lower level
- **Sizing mode** on an all-liquid inlet with no `D1_m`/`D2_m`/`d_m`, FL = 0.9 and Fd = 1 gives Kv equal to R0's. With no diameters, fluids sets `Rev = 1e5` and skips the laminar branch, so `allow_laminar` makes no difference.
  - Therefore `info["Cv"]` (R1) == `info["Cv"]` (R0, with Fp = 1) to 1e-12 relative, and the outlet state is identical (same flash).
  - This holds whenever the case is not choked, because Psat enters only the choke test. The R0 example case (propane, ΔP 172.4 kPa) is far from choke.
- **Rating mode:** with `Cv_rated` equal to R1's sizing Cv, `characteristic = "linear"` and `opening = 1.0`, the solved P2 equals the sizing `P_out` to 1e-8 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `0.001 < vapor_fraction < 0.999` | `ControlValveSpecError` (R0, imported) | "two-phase flow is outside IEC 60534-2-1" |
| both or neither of P_out/dP in sizing mode; P_out > P1 or ≤ 0; dP < 0 | `ControlValveSpecError` | as R0's `_outlet_pressure` (call it read-only) |
| rating mode without `Cv_rated` or `opening` | `ControlValveSpecError` | "rating mode needs Cv_rated and opening" |
| `opening` outside (0, 1] | `ControlValveSpecError` | "opening" |
| `characteristic` not one of linear/equal_percentage/quick_opening | `ControlValveSpecError` | "characteristic" |
| `rangeability` ≤ 1 | `ControlValveSpecError` | "rangeability" |
| FL, Fd or xT outside (0, 1] | `ControlValveSpecError` | the name |
| only some of D1_m/D2_m/d_m given; any ≤ 0; d_m > min(D1, D2) | `ControlValveSpecError` | "D1_m, D2_m, d_m" |
| diameters given in rating mode | `ControlValveSpecError` | "sizing mode only" |
| no viscosity available | `ControlValveSpecError` | "mu_liquid" / "mu_gas" |
| gas Z is None, or γ ≤ 1 | `ControlValveSpecError` | "z_factor" / "gamma" |
| sizing: required Cv > Cv_rated | `ControlValveSpecError` | "exceeds Cv_rated" |
| rating: Kv_avail < Kv_choke | `ChokedCapacityError(ControlValveSpecError)`, new in the owned module | "choked capacity" |
| brentq failure | `ControlValveRatingError(ControlValveSpecError)`, new | "did not converge" |
| zero pressure drop in sizing mode (P2 == P1) | `ControlValveSpecError` | "zero pressure drop" (Kv is unbounded) |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| P_out | number | Pa | sizing: one of P_out/dP | (0, P1] | outlet pressure |
| dP | number | Pa | sizing: one of P_out/dP | ≥ 0 | pressure drop |
| Cv_rated | number | US gpm/psi^0.5 | rating: required; sizing: optional | > 0 | rated (full-travel) Cv |
| opening | number | – | rating: required | (0, 1] | relative travel l |
| characteristic | string | – | "linear" | linear, equal_percentage, quick_opening | inherent characteristic |
| rangeability | number | – | 50 | > 1 | R for equal percentage |
| FL | number | – | 0.9 | (0, 1] | liquid pressure-recovery factor |
| Fd | number | – | 1.0 | (0, 1] | valve style modifier |
| xT | number | – | 0.7 | (0, 1] | pressure-differential ratio factor (gas) |
| D1_m, D2_m, d_m | number | m | all or none | > 0, d ≤ min(D1, D2) | upstream pipe, downstream pipe and valve diameters (sizing only) |
| mu_liquid | number | Pa·s | used only if the thermo has none | > 0 | liquid viscosity |
| mu_gas | number | Pa·s | used only if the thermo has none | > 0 | gas viscosity |

```yaml
type: object
properties:
  P_out: {type: number, description: 'sizing mode: outlet pressure, Pa'}
  dP: {type: number, description: 'sizing mode: pressure drop, Pa'}
  Cv_rated: {type: number, description: 'rated full-travel Cv (US); required in rating mode'}
  opening: {type: number, description: 'rating mode: relative travel in (0, 1]'}
  characteristic: {type: string, enum: [linear, equal_percentage, quick_opening], description: 'inherent characteristic, default linear'}
  rangeability: {type: number, description: 'equal-percentage rangeability R > 1, default 50'}
  FL: {type: number, description: 'liquid pressure-recovery factor, default 0.9'}
  Fd: {type: number, description: 'valve style modifier, default 1.0'}
  xT: {type: number, description: 'gas pressure-differential ratio factor, default 0.7'}
  D1_m: {type: number, description: 'upstream pipe ID, m (sizing; all three or none)'}
  D2_m: {type: number, description: 'downstream pipe ID, m'}
  d_m: {type: number, description: 'valve size, m'}
  mu_liquid: {type: number, description: 'liquid viscosity, Pa.s, if the thermo reports none'}
  mu_gas: {type: number, description: 'gas viscosity, Pa.s, if the thermo reports none'}
```

## Outputs
- **Port `outlet`:** `thermo.flash_ph(z, P2, h_in, F)`.
- **Balances:** `duty_W = 0`, `power_W = 0`. Isenthalpic, so V0 closes exactly.
- **info:**
  - `Kv_m3h_bar05` and `Cv`;
  - `choked` (0/1);
  - `dP_choke_Pa` (P1 − P2_choke);
  - `FR`, `FP` (1.0 when no fittings);
  - `x` and `Y` (gas only);
  - `P_out_Pa`;
  - `travel` (sizing with `Cv_rated`) or `opening` (rating);
  - `phase_code` (0 liquid, 1 gas);
  - `dT_K`.

## Tests
- **Closed-form** (pure functions; independent script `calc_control_valve.py` in this spec's folder, which reproduces the equations above, not fluids):
  - **L1** (ρ=965.4, Psat=70.1e3, Pc=22120e3, μ=3.1472e-4, P1=680e3, P2=220e3, Q=0.1 m³/s, FL=0.9, no fittings):
    - FF = 0.944237522523330;
    - ΔP_choke = 497185.249233603 Pa, so not choked;
    - **Kv = 164.995476370496**; Cv = 190.746215457220.
    - Q is 360 m³/h, ΔP 460 kPa, eq. 1.
  - **L2** (same, P2 = 100e3): choked. **Kv = 158.705448111403** (eq. 3).
  - **G1** (n=50 mol/s, T=433, MW=44.01, γ=1.30, Z=0.988, μ=1.4665e-4, P1=680e3, P2=450e3, xT=0.60):
    - Vm,std = 0.0224139695450141 m³/mol; Q_std = 1.12069847725071 m³/s;
    - x = 0.338235294117647, below Fγ·xT = 0.557142857142857, so not choked;
    - Y = 0.797637003519357; **Kv = 71.3395905795846**.
  - **G2** (same, P2 = 200e3): choked (x = 0.70588); **Kv = 66.5048538035932**. The choke P2 is 301142.857142857 Pa.
  - **Characteristics:**
    - eq% with R=50: φ(0.25)=0.0531829589694499, φ(0.5)=0.141421356237310, φ(0.8)=0.457305051927326;
    - quick opening: φ(0.5)=0.707106781186548;
    - inverse eq%: φ=0.2 → l = 0.588591910067779.
  - Tolerance 1e-10 relative.
- **Unit level:**
  - On the R0 example (propane), sizing mode: `Cv` matches R0 to 1e-12, and the outlet T, P and enthalpy are identical.
  - Rating identity, as stated above, to 1e-8.
  - Rating with equal percentage at opening 0.6 on the same valve: the solved P2 gives `kv_liquid(P2)` equal to Kv_avail to 1e-9 (the residual check).
  - A gas case (methane at 300 K, 5 MPa → 3 MPa): Kv_m3h_bar05 equals `kv_gas` called with the unit's own reported MW, Z, γ and n, and `Q_std = n·Vm,std` (the conversion check).
- **Identity:** the two reductions above.
- **Refusals:** one test per refusal-table row, each `pytest.raises(<class>, match=<fragment>)`. The choked-capacity refusal uses the L2-like liquid with `Cv_rated` set to 0.9 × the choked Cv at opening 1.
- **V1 candidates:**
  - IEC 60534-2-1:2011 Annex D (ISA-75.01.01-2007 Annex), Example 1 (water, globe valve, liquid) and Example 2 (ball valve). The inputs are printed: ρ1=965.4 kg/m³, P1=680 kPa, P2=220 kPa, Q=360 m³/h, T1=363 K, Psat=70.1 kPa, Pc=22120 kPa, ν=3.26e-7 m²/s, FL=0.9/0.6, Fd=0.46/0.98, D=d=150/100 mm. Example 3 covers gas (CO2, 433 K).
  - The implementer must transcribe the **printed** Kv from the standard; the fluids docstring numbers are model outputs and are not acceptable as expected values. Use `thermo: iapws_if97` for the water examples so that ρ and Psat track the printed state. Any density mismatch goes in `assessed` with the measured value.
  - If the standard is not accessible: V1 gap in the row notes, with search places: the IEC 60534-2-1 Annex D examples, the ISA-75.01.01 annex, and the Emerson Control Valve Handbook (5th ed.) ch. 5 worked liquid and gas sizing examples.

## Steps (each about 40 minutes, each ending in a push)
1. **Pure functions:** `kv_liquid`, `kv_gas`, `characteristic` and its inverse, and the Q_std conversion. Closed-form tests L1, L2, G1, G2 and the characteristics. Push and open the PR.
2. **The `ControlValveR1` adapter in sizing mode:** phase classification, property assembly, refusals, outlet, info, `example_case` (propane, R0 basis plus `Cv_rated`). The R0 identity test and the refusal tests. Push.
3. **Rating mode:** choke bracket, brentq, `ChokedCapacityError`, `ControlValveRatingError`. Rating identity and the eq% residual test. Push.
4. **Catalogue `levels.R1`:** adapter `ngdesign.units.flow.control_valve_r1:ControlValveR1`, `status: provisional`, the params schema above, note "IEC 60534-2-1 sizing/rating, choked flow, inherent characteristic", and validation ids. Add `cases/control_valve.yaml` (V1, or the gap in notes). Regenerate docs (`validate_units.py`, then `--audit` separately), run the gates, push and comment.

## Review checklist (for the orchestrator)
- The gas Q passed to fluids is **standard** volumetric flow (n·0.0224139695 m³/mol), not the actual flow.
- The Kv↔Cv constant is 0.865, the same as R0's `cv_liquid_isa`.
- ρ0 is not re-typed (fluids owns it).
- Psat for a mixture comes from `bubble_point(z, T=T1).P`, and pure-component Psat from `pure_psat`.
- The rating bracket is `[P2_choke, P1(1 − 1e-9)]`, with a capped brentq and a typed error at the cap.
- The identity to R0 holds at 1e-12 on R0's own example.
- Every refusal row has a test with a `match=`.
- The V1 expected values are the standard's printed numbers, not fluids docstring outputs.
