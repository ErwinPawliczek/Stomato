# electrolyser_stack R1: polarisation-curve stack (reversible voltage from formation data plus ohmic and activation overpotentials)

- **Family / package:** reactors, `src/ngdesign/units/reactors/`
- **Levels delivered:** R1 of row `electrolyser_stack`, from `planned` to `provisional` (the end state).
- **Depends on:** U-R2 conventions, U-01d (#243). The R0 adapter is merged (U-F).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/electrolyser_stack` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/reactors/electrolyser_r1.py` (new): adapter `ElectrolyserStackR1`.
  - `tests/units/reactors/test_electrolyser_stack_r1.py` (new).
  - `data/validation_units/reactors/cases/electrolyser_stack.yaml` (new).
  - The `levels.R1` entry of row `electrolyser_stack` in `data/unit_models/reactors.yaml`, plus that row's `notes` line. Leave `levels.R0` untouched; `end_state: true` stays on R1.
- **Read-only imports (verified to exist):**
  - `ngdesign.units.reactors.electrolyser.ElectrolyserStack`: the R0 adapter, called by composition. Do not edit `electrolyser.py`.
  - `ngdesign.units.reactors.electrolyser.FARADAY` (96485.33212)
  - `ngdesign.units._physics.kinetics.ln_keq(reaction, T) -> float` (the `from_gibbs` path: the single owner of ΔG°(T)) and `R`
  - `ngdesign.contracts.reactions.Reaction` and `Equilibrium`
  - `Thermo.pure_psat(cid: str, T: float) -> float | None`
- **Current state:** R0 `ElectrolyserStack` (`electrolyser.py`).
  - Params: `current_A`, `n_cells`, `cell_voltage_V` (an input) and `faradaic_efficiency` (default 1).
  - H2O is consumed at n_H2 = η_F·I·N/(2F). H2 leaves pure on `h2_out`; everything else, including O2, on `o2_out`. Power = V·I·N; isothermal duty.
  - R1 replaces the voltage input with a polarisation curve.

## Method

### Equations
1. **Reversible voltage, vapour-water reactant.** H2O(g) → H2 + ½O2:
   U_rev,g(T) = ΔG°(T)/(2F) = −R·T·ln K(T)/(2F), with ln K from `ln_keq` on that reaction (`equilibrium: {form: from_gibbs}`). This uses the ideal-gas 1-bar standard state (JANAF-style path in `kinetics.ln_keq`).
2. **Liquid-water reactant.** Using μ_H2O(l) = μ°_ig + R·T·ln(p_sat/P°) (an ideal vapour in equilibrium with the liquid; Poynting neglected; P° = 1e5 Pa):
   U_rev,l(T) = [ΔG°(T) − R·T·ln(p_sat(T)/P°)]/(2F), with p_sat = `thermo.pure_psat("H2O", T)`.
3. **Optional Nernst pressure term** (`pressure_correction: true`; both products at the stack pressure P, dry gases):
   U_rev += (R·T/(2F))·ln[(P/P°)^{1.5}].
4. **Cell voltage.** The Ulleberg (2003) alkaline form, with T_C = T − 273.15 (°C) and current density i = I/A_cell (A/m²):
   U_cell = U_rev + (r1 + r2·T_C)·i + s·log10[(t1 + t2/T_C + t3/T_C²)·i + 1].
   - Ulleberg, *Int. J. Hydrogen Energy* 28 (2003) 21–33, eq. 4.
   - **The implementer must confirm the logarithm base and the coefficient units against the printed equation** before shipping the `ulleberg2003` preset. The generic form above is what the adapter implements for user-supplied coefficients, with log10 as stated.
5. **Faradaic efficiency** (Ulleberg 2003, eq. 9 form): η_F = f2·i²/(f1 + i²), with f1 in A²/m⁴. If `faradaic` is absent, η_F = 1.

### Algorithm
1. **Validate** the params. The inlet must be single-phase: a vapour fraction of 0 means a liquid reactant and equation 2; 1 means vapour and equation 1. Two-phase raises `ElectrolyserError`. The stack temperature T is `T_K`, default the inlet T.
2. **Compute** U_rev from equations 1–3, U_cell from equation 4 and η_F from equation 5.
3. **Delegate to R0.** `ElectrolyserStack().solve(inlets, {"current_A": I, "n_cells": N, "cell_voltage_V": U_cell, "faradaic_efficiency": η_F}, thermo)`. R0 owns the Faraday split, the power and the isothermal energy closure, and the R1 result is R0's result. The outlets leave at R0's temperature; if `T_K` differs from the inlet T, refuse rather than re-heat. R0 is isothermal at the inlet T, and changing that would edit R0's behaviour.
4. **Info.** R0's `info` plus `U_rev_V`, `eta_ohmic_V`, `eta_activation_V`, `cell_voltage_V`, `current_density_A_m2`, `faradaic_efficiency`, and `efficiency_HHV`. The last is the thermoneutral voltage R0 already reports, divided by U_cell.

### Reduction to the lower level
With r1 = r2 = s = 0, `pressure_correction` false and `faradaic` absent, U_cell = U_rev and η_F = 1. The R1 `UnitResult` then equals `ElectrolyserStack().solve(inlets, {current_A, n_cells, cell_voltage_V: U_rev, faradaic_efficiency: 1.0})` exactly (1e-12 on every outlet number, duty and power). It is the same code path.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `area_m2` ≤ 0; `current_A` ≤ 0; `n_cells` < 1 | `ElectrolyserError` (ValueError) | the parameter name |
| T_C ≤ 0 °C while t2 or t3 is nonzero (the log argument diverges) | `ElectrolyserError` | `T_C` |
| log argument (t1 + t2/T_C + t3/T_C²)·i + 1 ≤ 0 | `ElectrolyserError` | `activation term` |
| two-phase inlet | `ElectrolyserError` | `two-phase` |
| liquid inlet and `pure_psat` returns None | `ElectrolyserError` | `saturation pressure` |
| `T_K` given and ≠ the inlet T | `ElectrolyserError` | `T_K` |
| preset `ulleberg2003` requested before its coefficients are transcribed with a citation | `ElectrolyserError` | `preset` |
| R0 refusals (H2/O2 in feed, water short, …) | `ValueError`, from R0 | as in R0 |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| current_A | number | A | required | > 0 | stack current |
| n_cells | number | — | required | ≥ 1 | cells in series |
| area_m2 | number | m² | required | > 0 | active area per cell |
| polarisation | object | — | required | — | `{"r1": Ω·m², "r2": Ω·m²/°C, "s": V, "t1": m²/A, "t2": m²·°C/A, "t3": m²·°C²/A}`, or `"ulleberg2003"` (a preset; only once transcribed with a citation) |
| faradaic | object | — | absent (η_F = 1) | f1 > 0, f2 in (0, 1] | `{"f1": A²/m⁴, "f2": —}` |
| pressure_correction | boolean | — | false | — | add the Nernst term (equation 3) at the inlet P |
| T_K | number | K | inlet T | must equal the inlet T | stack temperature (documented check) |

```yaml
params:
  type: object
  required: [current_A, n_cells, area_m2, polarisation]
  properties:
    current_A: {type: number, description: stack current, A}
    n_cells: {type: number, description: cells in series}
    area_m2: {type: number, description: active area per cell, m2}
    polarisation: {description: "{r1, r2, s, t1, t2, t3} Ulleberg-form coefficients (T in degC, i in A/m2), or 'ulleberg2003' once transcribed"}
    faradaic: {type: object, description: "{f1 A2/m4, f2}: eta_F = f2 i^2/(f1 + i^2); absent = 1"}
    pressure_correction: {type: boolean, description: Nernst term at the stack pressure; default false}
    T_K: {type: number, description: stack temperature, K; must equal the inlet temperature at R1}
```

## Outputs
- Ports `h2_out` and `o2_out` exactly as in R0.
- `power_W` = U_cell·I·N; `duty_W` is R0's isothermal closure.
- V0 on `mass_elements` and the formation basis at 1e-8, inherited from R0.

## Tests
- **Closed-form, U_rev at 298.15 K** (`calc_electrolyser_stack.py`). With the databank values H2O(g) Hf = −241822 J/mol and S = 188.8, H2 S = 130.7, O2 S = 205.2 J/(mol·K), at 298.15 K ln_keq's ∫ΔCp terms vanish, so:
  - ΔS = 44.5 J/(mol·K) and ΔG° = 228554.325 J/mol, giving **U_rev,g = 1.18439933 V**.
  - With `pr` p_sat(H2O, 298.15 K) = 3169.92934 Pa (read from the package in the test as an input): ΔG_l = 237110.348 J/mol, giving **U_rev,l = 1.22873779 V**.
  - Tolerance 1e-9 relative. The printed textbook value of 1.229 V is a sanity check, not the assertion.
- **Closed-form, polarisation.** Test coefficients, which are not data: r1 = 8.0e-5, r2 = −2.5e-7, s = 0.185, t1 = −0.1, t2 = 8.4, t3 = 247.0. With I = 2000 A, A = 0.25 m², N = 10 and a liquid water feed at 298.15 K (T_C = 25):
  - i = 8000 A/m², ohmic term = 0.59 V, activation = 0.68511845 V, so **U_cell = 2.50385624 V**.
  - With f1 = 2.5e4 and f2 = 0.96: **η_F = 0.959625146**, n_H2 = 0.0994581379 mol/s, and P_el = 50077.1249 W.
  - Tolerance 1e-9 relative.
- **Identity:** the reduction above, at 1e-12.
- **Refusals:** one per refusal-table row.
- **V1:** Ulleberg 2003 prints the coefficient table (Table 1) and polarisation curves, mostly as figures.
  - A V1 case needs a *printed* (current, voltage, temperature) point with the stack area, from a table or the text.
  - Search Ulleberg 2003 (Tables 1–2 and the text), Ursúa, Gandía & Sanchis, *Proc. IEEE* 100 (2012) 410–426, and the LeRoy/Bowen/LeRoy 1980 alkaline data.
  - If no printed point exists, ship a V1 gap naming those searches. The `ulleberg2003` preset is added only when the Table 1 values are transcribed with page and equation numbers.

## Steps (each about 40 minutes, each ending in a push)
1. **Voltage and efficiency.** `electrolyser_r1.py`: `ElectrolyserError`, U_rev (equations 1–3) via `ln_keq` and `pure_psat`, U_cell (equation 4) and η_F (equation 5). Tests: U_rev closed form and polarisation closed form at the function level.
2. **Adapter.** `ElectrolyserStackR1` delegating to R0, its info and `example_case` (R0's water feed, test coefficients). Tests: the identity and the refusals.
3. **Catalogue.** YAML `levels.R1`, `cases/electrolyser_stack.yaml` (V1 or gap), harness write and `--audit`. Open the PR.

## Review checklist (for the orchestrator)
- ΔG°(T) comes only from `kinetics.ln_keq` (no re-derivation). The liquid correction uses `pure_psat` with P° = 1e5 Pa.
- log10 is used, and the coefficient units match the params table. The preset is gated on a citation.
- R0 is called by composition, `electrolyser.py` is untouched, and the identity holds at 1e-12.
- No silent re-heating to `T_K`.
