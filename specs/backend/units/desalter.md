# desalter R1: Stokes settling with a two-population drop model (water carryover and salt removal from T, wash rate and vessel area)

> **BLOCKED on a property prerequisite (orchestrator decision needed before dispatch).** Measured on main, 2026-10-25, at 403.15 K and 1 MPa, using `phase_props` on the example slate (`bagajewicz_ji_2001_light`, 48 pseudos) and on pure water:
>
> | package | oil density (kg/m³) | water density (kg/m³) | viscosity |
> |---|---|---|---|
> | `pr` | 563.0 | 777.3 | None |
> | `pr78` | 567.9 | 777.3 | None |
> | `srk` | 504.2 | 688.6 | None |
> | `api-srk` | 504.5 | 688.6 | None |
> | `pr-peneloux` | 877.6 | 774.6 | None |
> | `srk-peneloux` | 844.3 | 791.0 | None |
>
> Real values are about 800–850 for the oil and about 935 for water at 130 °C. Every package returns `viscosity = None` for the pseudo-component oil. The Peneloux packages even invert the density difference: water drops would *rise*.
>
> Stokes settling is driven by Δρ/μ_o, so R1 cannot get honest inputs through the Thermo contract today. Two ways forward:
> - **(A, recommended)** A thermo-side prerequisite, owned outside this unit: pseudo-component liquid viscosity (for example a cited dead-oil correlation on the assay API gravity) and a liquid-water density that is correct at T. Dispatch this spec unchanged once those are available through `phase_props`.
> - **(B, interim)** Make `rho_oil_kg_m3`, `rho_water_kg_m3` and `mu_oil_Pa_s` **required params**. The ΔT effect is then the user's to supply, the level note must say "temperature effect via user-supplied properties", and the monotonic-in-T test is dropped.
>
> Under (B) the Algorithm's step 3 reads the params instead of thermo, and nothing else changes. Do not dispatch until the orchestrator picks (A) or (B).

- **Family / package:** refining, `src/ngdesign/units/refining/`
- **Levels delivered:** R1, from `planned` to `provisional` (`end_state`)
- **Depends on:** U-R2 conventions, U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/desalter` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/refining/desalter_r1.py` (new)
  - `tests/units/refining/test_desalter_r1.py` (new)
  - `data/validation_units/refining/cases/desalter.yaml` (new, only if a V1 case lands)
  - `data/unit_models/refining.yaml`: only `levels.R1` of row `desalter`, plus its `notes` line
- **Read-only imports (verified on main):**
  - `ngdesign.units.refining.desalter.Desalter` (R0; `example_case()`, `solve(inlets, params, thermo)`), `SALT_ID = "NaCl"`, `WATER_ID = "H2O"`
  - `ngdesign.units.refining._cuts.RefiningSpecError`, `require_float(params, key) -> float`, `optional_float(params, key, default) -> float`
  - `Thermo.phase_props(composition, T, P, kind: PhaseKind) -> PhaseProps`, which carries `density` (kg/m³) and `viscosity` (Pa·s, may be None)
  - `ngdesign.contracts.PhaseKind`: members `VAPOR`, `HC_LIQUID`, `AQUEOUS`, `SOLID` (verified)
- **Current state:** R0 = `ngdesign.units.refining.desalter:Desalter`.
  - Isothermal at T with dP. `water_carryover_frac` of all water reports to the crude, and `salt_removal` of the crude's NaCl leaves with the brine; both are user inputs. Non-water wash components go to the brine.
  - Ports: `crude_in`, `wash_in` → `crude_out`, `water_out`.
  - V1 gap is recorded in the row notes (PetroWiki and Wauquier searched; no printed worked case).

## Method
**Why this model:** no open source with printed numbers gives a desalting-efficiency correlation in wash rate and ΔT; the row's own V1 search found none. R1 therefore *computes* R0's two split parameters from a cited physical model. Temperature enters through the oil viscosity and the density difference (thermo at T); wash rate enters through the dilution of the emulsified brine.

### Equations
1. Upward oil velocity in the settling zone: `U = Q_oil/A`.
   - `Q_oil` is the volumetric flow of the water- and salt-free crude at (T, P_out), from `phase_props(crude_hc, T, P_out, HC_LIQUID).density`;
   - `A` (param `settling_area_m2`) is the horizontal cross-section the oil rises through.
2. Stokes terminal velocity of a water drop (Stokes 1851; Perry's *Chemical Engineers' Handbook*, gravity decanters): `v(d) = g·d²·(ρ_w − ρ_o)/(18·μ_o)`. A drop settles against the rising oil only if `v(d) > U` (counter-current vertical settling). The cut diameter is `d_c = sqrt(18·μ_o·U / (g·(ρ_w − ρ_o)))`.
3. Drop-size distribution by volume, Rosin & Rammler (1933, J. Inst. Fuel 7, 29–36): `F(d) = 1 − exp(−(d/d̄)^n)`, with `d̄ = d50/(ln 2)^(1/n)`, so that F(d50) = 0.5.
4. Two water populations:
   - **mixed:** the fraction ε (`mixing_efficiency`) of the crude's brine B has coalesced with all the wash water W. Its drops have median `d50_mixed` (the electrostatic coalescence result, a user input).
   - **fine:** the rest, (1 − ε)·B, stays as fine original emulsion drops with median `d50_fine`.

   Carryover fractions: `c_m = F(d_c; d50_mixed)` and `c_f = F(d_c; d50_fine)`.
5. Water to `crude_out`: `w_c = c_m·(ε·B + W) + c_f·(1 − ε)·B`. Salt S (NaCl in crude_in) to `crude_out`: `S·(ε·c_m + (1 − ε)·c_f)`. The salt of the mixed pool is uniform in the mixed water; the fine pool keeps its original brine.
6. The R0-equivalent splits are `water_carryover_frac = w_c/(B + W)` and `salt_removal = 1 − (ε·c_m + (1 − ε)·c_f)`.

ρ_w is the water liquid density at (T, P_out) from `phase_props({"H2O": 1.0}, T, P_out, PhaseKind.AQUEOUS)`. ρ_o and μ_o come from the HC_LIQUID phase props of the crude without H2O and NaCl. g = 9.80665 m/s².

### Algorithm
1. Validate the params, and run R0's own validation by reusing its parsing: T, dP, P_out = crude_in.P − dP.
2. B = crude_in's H2O molar flow; W = wash_in's H2O molar flow; S = crude_in's NaCl molar flow (0 allowed).
3. Properties at (T, P_out): ρ_o, μ_o, ρ_w. Refuse if μ_o is None or ρ_w ≤ ρ_o.
4. Compute U, d_c, c_m, c_f, `water_carryover_frac` and `salt_removal` per the equations. No iteration.
5. Call `Desalter().solve(inlets, {"T": T, "dP": dP, "water_carryover_frac": wc, "salt_removal": sr}, thermo)`. R0 is the one owner of the split, the flashes and the duty.
6. Add the R1 info keys to R0's info and return R0's outlets and duty unchanged.

### Reduction to the lower level
Exact by construction: R1 = R0 evaluated at the computed `(water_carryover_frac, salt_removal)`. The identity test compares R1 with a direct R0 call at those two numbers, field for field with `==`. Physical limits:
- `settling_area_m2 → ∞` gives d_c → 0, c_m = c_f = 0, so no carryover and full salt removal;
- `ε = 1` gives salt removal = 1 − c_m.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `settling_area_m2` ≤ 0 | `RefiningSpecError` | `settling_area_m2` |
| `d50_mixed_um` or `d50_fine_um` ≤ 0 | `RefiningSpecError` | `d50` |
| `rosin_rammler_n` ≤ 0 | `RefiningSpecError` | `rosin_rammler_n` |
| `mixing_efficiency` outside [0, 1] | `RefiningSpecError` | `mixing_efficiency` |
| `water_carryover_frac` or `salt_removal` passed (R0 inputs; R1 computes them) | `RefiningSpecError` | `computed at R1` |
| ρ_w ≤ ρ_o at (T, P) (no settling) | `RefiningSpecError` | `density` |
| oil viscosity unavailable from thermo | `RefiningSpecError` | `viscosity` |
| crude without water (B = 0) and wash without water (W = 0) | `RefiningSpecError` | `water` |

## Params
| name | type | unit | required/default | meaning |
|---|---|---|---|---|
| `T` | number | K | required | desalter temperature (R0 meaning) |
| `dP` | number | Pa | default 0 | pressure drop (R0 meaning) |
| `settling_area_m2` | number | m² | required | horizontal area for the oil's upward flow |
| `d50_mixed_um` | number | µm | required | median drop diameter of the coalesced wash and brine water |
| `d50_fine_um` | number | µm | required | median drop diameter of the uncontacted brine emulsion |
| `rosin_rammler_n` | number | — | required | Rosin-Rammler spread exponent |
| `mixing_efficiency` | number | — | required | ε, the fraction of brine contacted by the wash water |

No default for any physical parameter: the user supplies their vessel and emulsion data.

```yaml
params:
  type: object
  required: [T, settling_area_m2, d50_mixed_um, d50_fine_um, rosin_rammler_n, mixing_efficiency]
  additionalProperties: false
  properties:
    T: {type: number, description: desalter temperature (K), isothermal}
    dP: {type: number, description: pressure drop from the crude inlet (Pa, default 0)}
    settling_area_m2: {type: number, exclusiveMinimum: 0, description: horizontal area the oil rises through (m2)}
    d50_mixed_um: {type: number, exclusiveMinimum: 0, description: volume-median drop diameter of the coalesced wash+brine water (micrometre)}
    d50_fine_um: {type: number, exclusiveMinimum: 0, description: volume-median drop diameter of the uncontacted brine emulsion (micrometre)}
    rosin_rammler_n: {type: number, exclusiveMinimum: 0, description: Rosin-Rammler spread exponent of both populations}
    mixing_efficiency: {type: number, minimum: 0, maximum: 1, description: fraction of the crude brine contacted by the wash water}
```

## Outputs
- `crude_out`, `water_out` and `duty_W` exactly as R0 produces them at the computed splits. `power_W = 0`.
- `info`: R0's keys (`bsw_vol_pct`, `salt_removed_frac`, `salt_tracked`), plus `oil_velocity_m_s`, `cut_diameter_um`, `carryover_mixed`, `carryover_fine`, `water_carryover_frac`, `salt_removal`, `rho_oil_kg_m3`, `rho_water_kg_m3`, `mu_oil_Pa_s`.

## Tests
- **Closed-form (pure arithmetic; script `calc_desalter.py`):** a module-level function `_splits(Q_oil, A, rho_o, rho_w, mu_o, d50_mixed, d50_fine, n, eps, B, W)` returns (U, d_c, c_m, c_f, water_carryover_frac, salt_removal). Test it directly with literals:
  - inputs: Q_oil = 0.1 m³/s, A = 200 m², ρ_o = 850, ρ_w = 935 kg/m³, μ_o = 2.0e-3 Pa·s, d50_mixed = 300 µm, d50_fine = 20 µm, n = 2.5, ε = 0.9, B = 10 mol/s, W = 50 mol/s;
  - expected (rel 1e-10): U = 0.0005 m/s; d_c = 1.46948938045e-4 m; c_m = 0.109877430067; c_f = 1.0 (to double precision); water_carryover_frac = 0.124712806232; salt_removal = 0.80111031294.
- **Identity to R0:** on the R0 `example_case` feeds, with R1 params A = 200, d50s 300/20, n = 2.5, ε = 0.9, R1's outlets and duty `==` `Desalter().solve` at `info["water_carryover_frac"]` and `info["salt_removal"]`.
- **Monotonicity (physics direction):** with everything else fixed:
  - raising T must not increase `water_carryover_frac` (μ_o falls). Assert this on the example at T = 393.15 vs 413.15 K, and record the measured numbers in the comment;
  - raising `settling_area_m2` must not increase it.
- **Limits:** `settling_area_m2 = 1e9` gives `water_carryover_frac` < 1e-12 and `salt_removal` > 1 − 1e-12.
- **Refusals:** one per row of the table.
- **V1:** gap; keep the existing row-notes gap. Search Wauquier, *Petroleum Refining* vol. 1 (crude desalting), and Abdul-Wahab et al. (2006, *Desalination* 201) for an industrial desalter data set with printed inputs (T, wash %, vessel) and outputs (salt in and out). Use one only if every input this model needs is printed; otherwise record the gap. Never fit or reconstruct.

## Steps
1. **`_splits` and its closed-form test (≈30 min).** Push and open the PR.
2. **The adapter (thermo properties, R0 delegation, info), the identity test and the refusals (≈40 min).** Push.
3. **Monotonicity and limit tests, `example_case` (R0 feeds plus the R1 params above), catalogue flip, docs and gates (≈35 min).** The row's R1 note: "Stokes cut (counter-current settling) + Rosin-Rammler two-population carryover; splits fed to R0". Push.

## Review checklist
- `d_c` uses the upward OIL velocity and μ of the OIL (the continuous phase).
- Rosin-Rammler is on a volume basis, with d̄ derived from d50 through (ln 2)^(1/n).
- µm to m conversions.
- The salt formula weights c_m by ε and c_f by (1 − ε).
- R0 owns the outlets (no second split implementation).
- No physical defaults.
- ρ_w comes from the thermo phase props at T, never a literal 1000.
