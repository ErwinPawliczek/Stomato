# cstr R1, R2: kinetic CSTR (algebraic extents; R2 with VLE in the vessel)

- **Family / package:** reactors, `src/ngdesign/units/reactors/`
- **Levels delivered:** R1 and R2 of row `cstr`, each from `planned` to `provisional`. Two PRs: R1, then R2 after R1 merges.
- **Depends on:** U-R2 conventions, U-01d (#243), U-R (#199, merged).
- **Wave/order:** parallel-safe: independent of pfr, shares no file with it.
- **Branch:** `u-lv/cstr` (R1), `u-lv/cstr-r2` (R2) · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/reactors/cstr.py` (new): adapters `CstrR1` and `CstrR2`, plus the private Newton solver.
  - `tests/units/reactors/test_cstr_r1.py`, `test_cstr_r2.py` (new).
  - `data/validation_units/reactors/cases/cstr.yaml` (new).
  - The `levels.R1` and `levels.R2` entries of row `cstr` in `data/unit_models/reactors.yaml`, plus that row's `balance: mass_elements` key (added in the R1 PR) and its `notes` line.
- **Read-only imports (verified to exist):**
  - `ngdesign.units._physics.kinetics.rate(reaction, T, P, z) -> float`
  - `ngdesign.units._physics.kinetics.apply_extents(n_in, rset, extents) -> dict[str, float]`, which raises `ReactionExtentError`
  - `ngdesign.units._physics.kinetics.enthalpy_with_formation(state) -> float` (W)
  - `ngdesign.units._physics.kinetics.R`
  - `ngdesign.units.reactors._shared.reaction_set_param`, `thermal_outlet(inlet, n_out, thermal, thermo)`, `z_from`
  - `numpy.linalg.solve`; `Thermo.flash_pt`; `Phase.density`, `.molecular_weight`, `.kind`, `.mole_fraction`, `.composition`
- **Current state:** the row has only `planned` levels; there is no adapter.

## Method

### Equations
1. **Mole balance per reaction** (Fogler, *Elements of CRE*, CSTR design equation V = F_A0·X/(−r_A), evaluated at outlet conditions), written in extents:
   g_j(ξ, T) = |ν_base,j|·ξ_j − s_j·V_r·r_j(T, P_eff, z_out(ξ)) = 0.
   - z_out = F_out/ΣF_out, with F_out = `apply_extents(F_in, rset, ξ)`.
   - s_j is the rate-units scale: 1 for per-m³ rates, ρ_b for per-kg_cat rates. It uses the same accepted `rate_units` strings as the pfr spec's equation 3, so the two read identically.
2. **Concentration-equivalent pressure** for the reacting phase: P_eff = P for vapour (the contract's ideal-gas c = yP/RT) and P_eff = 1000·ρ/MW·R·T for liquid. This is identical to the pfr spec's equation 4.
3. **Energy** (adiabatic and fixed-duty modes; formation basis):
   g_T(ξ, T) = [ enthalpy_with_formation(flash_pt(z_out, T, P, ΣF_out)) − enthalpy_with_formation(inlet) − Q ] / (ΣF_in · 30 J/(mol·K) · 1 K) = 0.
   - Q = 0 when adiabatic, Q = duty_W for fixed duty.
   - The scale 30 J/(mol·K) is a fixed nominal c_p. It normalizes the residual only, never the solution.
4. **R2, phase-resolved rate** (VLE in the vessel; Fogler ch. 8 multiphase CSTR assumption: the vessel holdup has the outlet phase ratio, with no slip):
   r_j,vessel = V_k·r_j(T, P_eff,k, x_k), where k is the reacting phase.
   - V_k = V_r·(n_k·MW_k/ρ_k)/Σ_p(n_p·MW_p/ρ_p), from the flash phases at (z_out, T, P). The param `holdup_m3` overrides V_k when given.
   - If phase k is absent at a state, its rate is 0.

### Algorithm
1. **Resolve inputs.** Resolve the set (`reaction_set_param`) and check rate units. Refuse PowerLaw + `equilibrium` without `reverse`, as in the pfr spec (`kinetics.rate` applies (1 − 1/K) with no reaction quotient).
2. **Unknowns.** u = ξ (m values) for `"isothermal"` and `{"T_out": K}`, with T fixed at T_in or T_out. u = [ξ, T] for `"adiabatic"` and `{"duty_W": W}`. P is the inlet pressure throughout; the outlet has no pressure drop.
3. **Start.** ξ⁰ = 0 and T⁰ = `T_guess_K` if given, else T_in. The `T_guess_K` param selects a branch when an exothermic adiabatic CSTR has multiple steady states. The returned state is the one reached from this start, and the start is documented in `info`.
4. **Newton.**
   - Residual vector [g_j/ΣF_in, g_T].
   - Forward-difference Jacobian with steps h_ξ = 1e-7·max(|ξ_j|, 1e-6·ΣF_in) and h_T = 1e-6 K.
   - Step from `numpy.linalg.solve`; a singular matrix raises `CstrConvergenceError`.
   - Backtracking: halve α from 1 while any outlet amount < 0 or ‖g(u + αΔ)‖₂ ≥ ‖g(u)‖₂, at most 30 halvings.
   - Converged when ‖g‖∞ ≤ 1e-12 and ‖αΔ_ξ‖∞ ≤ 1e-12·ΣF_in.
   - **Cap: 100 iterations**, then `CstrConvergenceError` with the last ‖g‖∞.
5. **Phase check (R1).** On every residual evaluation, the flash at (z_out, T, P) must be single-phase in the declared `reacting_phase`: a vapour fraction ≤ 1e-9 for liquid, ≥ 1 − 1e-9 for vapour. Otherwise raise `CstrPhaseError` naming T, P and the vapour fraction ("two phases in the vessel; use level R2").
6. **Outlet.** `thermal_outlet(inlet, F_out(ξ*), mode, thermo)` closes the energy balance on the formation basis, for every mode.
   - For the adiabatic and duty modes this reproduces T* to within the Newton residual. Report `T_newton_K` and `T_closure_gap_K`.
   - Info: `extent_<id>_mol_s`, `conversion_<base>_<id>` and `newton_iterations`.

### Reduction to the lower level
- **R2 → R1:** when the flash at the converged state is single-phase in the reacting phase and `holdup_m3` is absent, V_k = V_r, and R2 equals R1 to 1e-12 relative (same residuals).
- **R1:** this is the row's first level. Identity: with all k0 = 0, ξ* = 0 and the outlet equals the inlet re-flashed, with an isothermal duty below 1e-9 W.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `volume_m3` ≤ 0 | `CstrError` (ValueError) | `volume_m3` |
| unknown `rate_units`; catalyst basis without `bulk_density_kg_m3` | `CstrError` | `rate_units` / `bulk_density_kg_m3` |
| reaction without kinetics; equilibrium without explicit reverse | `CstrError` | `has no kinetics` / `explicit reverse` |
| bad `thermal` mode | `ValueError`, raised by `thermal_outlet` | `thermal mode` |
| Newton cap or singular Jacobian | `CstrConvergenceError` (CstrError) | `did not converge` / `singular` |
| R1 two-phase vessel | `CstrPhaseError` (CstrError) | `use level R2` |
| R2: `reacting_phase` not in {vapor, hc_liquid, aqueous}; `holdup_m3` ≤ 0 or > `volume_m3` | `CstrError` | the parameter name |

## Params
**R1**

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| reaction_set | object/str | — | required | — | inline ReactionSet |
| volume_m3 | number | m³ | required | > 0 | reacting volume |
| thermal | str/object | — | `"isothermal"` | `"isothermal"`, `"adiabatic"`, `{"duty_W"}`, `{"T_out"}` | energy mode |
| reacting_phase | str | — | `"vapor"` | `"vapor"`, `"liquid"` | single phase required in R1 |
| bulk_density_kg_m3 | number | kg/m³ | required for per-kg_cat rates | > 0 | catalyst bulk density |
| T_guess_K | number | K | T_in | > 0 | Newton start; selects the steady-state branch |

**R2** keeps every R1 param and changes or adds:

| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| reacting_phase | str | — | `"hc_liquid"` | `"vapor"`, `"hc_liquid"`, `"aqueous"` | phase the reactions occur in |
| holdup_m3 | number | m³ | phase-ratio holdup | (0, volume_m3] | explicit reacting-phase volume |

JSON-schema fragment for R1:
```yaml
params:
  type: object
  required: [reaction_set, volume_m3]
  properties:
    reaction_set: {description: inline ReactionSet, or a string id resolved against Flowsheet.reactions}
    volume_m3: {type: number, description: reacting volume, m3}
    thermal: {description: "'isothermal' | 'adiabatic' | {duty_W: W} | {T_out: K}; default isothermal"}
    reacting_phase: {type: string, enum: [vapor, liquid], description: single phase required at R1; default vapor}
    bulk_density_kg_m3: {type: number, description: catalyst bulk density, kg/m3}
    T_guess_K: {type: number, description: Newton start temperature, K; selects the steady-state branch}
```

## Outputs
- Port `outlet`: the well-mixed effluent at the vessel state from `thermal_outlet`. In R2 it may be two-phase.
- `duty_W` is the heat added to the process; `power_W` is 0.
- V0 closes on `mass_elements` and the formation basis at 1e-8.

## Tests
- **Closed-form, R1-A** (isothermal first order, gas; `calc_cstr.py`):
  - Case: the pfr spec's R1-A reaction and feed (nC4 → iC4, k0 1.0e3 s⁻¹, Ea 5.0e4, 500 K, 2.0e5 Pa, 1.0 mol/s), with V = 2.0 m³.
  - X = Da/(1 + Da) with Da = 0.575299226.
  - Result: **X = 0.365199967**, F_nC4 = 0.634800033 mol/s. Tolerance 1e-9 relative.
- **Closed-form, R1-B** (isothermal second order with Δn ≠ 0):
  - Case: 2 C2H4 → 1-butene, base C2H4 (ν = −2), k0 = 5.0e-3 m³/(mol·s), Ea = 0, order 2 in C2H4, concentration basis. Feed: pure C2H4 at 1.0 mol/s, 600 K, 5.0e5 Pa. V = 0.5 m³.
  - The hand equation is 2ξ = V·k·(y_A·P/RT)², with y_A = (F0 − 2ξ)/(F0 − ξ), solved independently by brentq.
  - Result: c = 100.226963 mol/m³, **ξ = 0.447862522 mol/s** (X = 0.895725045), F_C2H4 = 0.104274955, F_1-butene = 0.447862522. Tolerance 1e-9 relative.
- **Closed-form, R2** (consistency: no printed closed form exists for a VLE CSTR):
  - Case: a liquid-phase isomerisation in a vessel flashed two-phase (for example nC5 → iC5 in liquid at a T/P inside the two-phase region, on `pr`).
  - The test recomputes, independently of the adapter, V_L = V·(n_L·MW_L/ρ_L)/Σ(n·MW/ρ) and r = k·x_nC5·c_L from the returned outlet's own liquid `Phase`.
  - It asserts |ν|·ξ_reported = V_L·r to 1e-9 relative.
- **Identity:** R2 → R1 on a single-phase liquid case (1e-12), and R1 with k0 = 0.
- **Adiabatic:** an exothermic case closes V0 at 1e-8, with `abs(T_closure_gap_K)` < 1e-6 K. `T_guess_K` reaching a different branch gives a different, still V0-closed state when multiplicity exists. Use Fogler's adiabatic-CSTR multiplicity example parameters only if V1 confirms them; otherwise any exothermic case on `pr`.
- **Refusals:** one test per refusal-table row. For example, R1 on a two-phase vessel, and a Newton cap forced by `T_guess_K` = 5 K.
- **V1 candidates:** Fogler, *Elements of CRE*, 4th ed.:
  - the isothermal liquid-phase CSTR design example producing ethylene glycol (the isothermal reactor design chapter; its chapter number varies by edition);
  - the adiabatic CSTR producing propylene glycol (propylene oxide + water, methanol diluent), in the non-isothermal chapter. The components exist in the databank.

  Confirm the example numbers and the printed inputs and results from the book. Otherwise ship a V1 gap naming the searches.

## Steps (each about 40 minutes, each ending in a push)
1. **R1 solver.** `cstr.py`: error classes, rate-units scale, P_eff, the residuals (equations 1–3), and Newton with backtracking and the cap. Tests R1-A and R1-B.
2. **R1 adapter.** `CstrR1`: thermal modes via `thermal_outlet`, the phase check, `example_case` (the R1-A feed), the k0 = 0 identity and the adiabatic V0 test. Refusals.
3. **R1 catalogue.** YAML `levels.R1` + `balance: mass_elements`, `cases/cstr.yaml` (V1 or gap), harness write and `--audit`. Open the R1 PR.
4. **R2** (new branch after R1 merges). The phase-resolved rate (equation 4), the `reacting_phase`/`holdup_m3` params and `CstrR2`. The R2 consistency test, R2 → R1 identity, R2 refusals and YAML `levels.R2` (`end_state` stays on R2). Open the R2 PR.

## Review checklist (for the orchestrator)
- The residual is evaluated at outlet conditions, and the extent divides by |ν_base|.
- Rate-units scale and P_eff are word-for-word the same as in the pfr spec. Ideally the shared helper is copied privately, so neither thread edits the other's file.
- Newton: FD steps, backtracking with non-negativity, the 100-iteration cap, typed errors and the `T_guess_K` start.
- The energy closure goes through `thermal_outlet`; `T_closure_gap_K` is reported.
- R2 holdup by phase volume fraction; an absent reacting phase gives rate 0; the identity holds at 1e-12.
- The equilibrium-without-reverse refusal is present.
