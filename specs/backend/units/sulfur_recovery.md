# sulfur_recovery R2: Gibbs equilibrium per catalytic converter (S6/S8 and optional COS/CS2), with R0's thermal stage and condensers

- **Family / package:** treating, `src/ngdesign/units/treating/`
- **Levels delivered:** R2, from `planned` to `provisional` (`end_state`), **partial by design**. Read "Scope limits" before dispatch.
- **Depends on:** U-R2 conventions, U-01d (#243).
- **Wave/order:** parallel-safe with every other unit. Two data and core issues limit its scope; see below.
- **Branch:** `u-lv/sulfur_recovery` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/treating/sulfur_recovery_r2.py` (new)
  - `tests/units/treating/test_sulfur_recovery_r2.py` (new)
  - `data/validation_units/treating/cases/sulfur_recovery.yaml` (new, only if a V1 case lands)
  - `data/unit_models/treating.yaml`: only `levels.R2` of row `sulfur_recovery`, plus its `notes` line. The row keeps `balance: mass_elements`.
- **Read-only imports (verified on main, 2026-10-25):**
  - `ngdesign.units._physics.gibbs.gibbs_minimum(species: Sequence[str], inerts: Sequence[str], n_in: Mapping[str, float], T: float, P: float) -> dict[str, float]` and `GibbsError(ValueError)`
  - `ngdesign.units.treating.sulfur_recovery.SulfurRecovery` (R0), `SulfurRecoveryError`, `_split_sulfur`, `_BURN_FRACTION`
  - `ngdesign.units._physics.kinetics.apply_extents`, `enthalpy_with_formation(state: StreamState) -> float`, `ReactionExtentError`
  - `ngdesign.contracts.reactions.ReactionSet`
  - `ngdesign.data.formation.formation_enthalpy_298(cid)`, `MissingFormationData`
- **Current state:** R0 = `ngdesign.units.treating.sulfur_recovery:SulfurRecovery`.
  - Thermal stage: burn one third of the H2S, then a Claus extent at `thermal_conversion`.
  - Catalytic stages: a given conversion, or equilibrium at T + `approach_K` for the single Claus reaction to S8.
  - Complete S8 condensation at `T_condenser`; duty on the formation basis.
  - Port `acid_gas_in` → `tail_gas_out`, `sulfur_out`. V1 `V1202-sulfur-recovery-gpsa`: GPSA Ex. 22-1 first-converter extent; the overall recovery is a documented gap.

## Scope limits (measured while writing this spec)
1. **No Gibbs furnace.** S2, the dominant sulfur species above about 1000 K, has no formation enthalpy and no critical constants in the databank: `component_record("S2")` raises `TypeError` on `Tcs[0] = None`, and `formation_enthalpy_298("S2")` fails. A Gibbs furnace without S2 would be physically wrong. R2 therefore keeps R0's thermal-stage rule unchanged. A data-layer prerequisite (S2 JANAF ideal-gas data plus a thermo-compatible record) un-defers a furnace step later. Not in this spec.
2. **No adiabatic converters — a stated modelling choice, not a defect.** The U-01b energy-basis defect (as measured when this spec was written) was fixed on main (#247/#252): `enthalpy_with_formation` now lifts by the constant ΔfH°298 on top of a package enthalpy that already carries the sensible heat from 298.15 K, and reaction enthalpies reproduce the databank heats of reaction. (Measured then, 298 → 500 K at 1 bar, the old lift read SO2 17560.6 J/mol where about 8800 is right; N2, an element, read 5916.9, correct.) R2 converters are **isothermal at the given stage T** because the plan scopes R2 to isothermal beds, as in R0; their heat release shows in the unit duty. Adiabatic beds remain a follow-up.
3. **Condenser stays R0's complete condensation.** The PR package's sulfur saturation pressure is unusable: `pure_psat("S8", 717.8 K)` = 5.29e5 Pa, against the normal boiling point's 1.013e5 Pa, about 5.2 times too high. A PR flash of the converter gas at 420 K puts 9 mol% water into the liquid sulfur. So the R2 condenser removes all S6 and S8, as R0 removes S8, and flashes `sulfur_out` with its own S6/S8 composition.

## Method
### Equations
Each catalytic converter i is at chemical equilibrium at T_eq,i = `T` + `approach_K` (approach default 0; the same "warmer, hence less converted" semantics as R0's approach). The method is Gibbs minimisation over the converter species set, ideal gas at P (`_physics/gibbs.py`: element-potential method; μ°_i(T) = ΔfH°298 − T·S°298 + ∫Cp dT − T·∫Cp/T dT; JANAF basis P° = 1 bar). Minimise G/RT = Σ n_i (μ°_i/RT + ln(y_i P/P°)) subject to A·n = b.

### Algorithm
1. **Validate the params.**
   - R0's keys: `T_thermal`, `P`, `T_condenser`, `thermal_conversion`, `reaction_set`. The reaction set is still required for the thermal stage.
   - `catalytic_stages`: a list of `{T, approach_K?}`. R2 has **no** `conversion` key; refuse it.
   - `extra_species`: optional list from {`COS`, `CS2`, `CO`, `H2`}.
2. **Thermal stage:** exactly R0. Reuse R0's code path by calling the same `apply_extents` sequence; copy R0's validation messages. Then split out the sulfur with `_split_sulfur`, so R0 condenses its S8 after the furnace.
3. **For each catalytic stage:**
   - species = sorted(the gas components present with n > 0) ∪ {S6, S8} ∪ `extra_species`;
   - **every** feed component goes into `species`, inerts included (N2, CO2), and `inerts = []`. This is required by `gibbs_minimum`: it counts inert atoms in the element budgets but refuses an element that no species carries. Measured: N2 passed as an inert raises `GibbsError("element 'N' ... carried by no species")`. An inert that is the only carrier of its element stays fixed by its budget automatically;
   - if any species lacks formation data, raise `SulfurRecoveryError` naming it (from `MissingFormationData`);
   - call `n = gibbs_minimum(species, [], gas, T_eq, P)`; on `GibbsError`, raise `SulfurRecoveryError(f"catalytic stage {i}: ...")`;
   - condense all S6 and S8 into the running sulfur total. Report the stage extents in `info`: `stage_{i}_H2S_conversion` = 1 − n_H2S,out/n_H2S,in, `stage_{i}_S6_mol_s`, `stage_{i}_S8_mol_s`, `stage_{i}_T_eq_K`.
4. **Outlets:**
   - tail gas = the remaining gas, `flash_pt` at (T_condenser, P);
   - `sulfur_out` = `flash_pt({S6, S8} at their summed composition, T_condenser, P, total)`. The thermal-stage sulfur is S8 (R0), and the catalytic stages add S6 and S8.
   - A zero-flow sulfur outlet follows R0's pattern.
5. **Duty:** `Σ enthalpy_with_formation(out) − Σ enthalpy_with_formation(in)`, R0's formula, on the corrected ΔfH°298 basis (#247/#252) and internally consistent with V0.
6. **`info`:** R0's keys, plus the per-stage keys above, `sulfur_recovery_fraction` on S atoms (6·S6 + 8·S8 over the feed S), and `species_set_size`.

### Reduction to the lower level
Exact (measured ≤ 1.4e-14; see Tests):
- With `extra_species = []` and the species set restricted to the R0 set (the test passes a private `_species_override` keyword to an internal function, never through the public params),
- the Gibbs minimum over {H2S, SO2, H2O, S8} plus fixed inerts at T_eq has exactly one degree of freedom (4 species, 3 elements H/O/S), which is the Claus extent.

So R2 equals R0's approach mode at the same T and `approach_K`. Tolerance: 1e-10 relative on species flows.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| a catalytic stage has `conversion` | `SulfurRecoveryError` | `conversion` and `R2` |
| a stage `T` ≤ 0 or `approach_K` < 0 | `SulfurRecoveryError` | `catalytic_stages[i]` |
| `extra_species` outside {COS, CS2, CO, H2} | `SulfurRecoveryError` | `extra_species` |
| a species without formation data | `SulfurRecoveryError` | (species id) |
| Gibbs failure | `SulfurRecoveryError` (wrapping `GibbsError`) | `catalytic stage` |
| R0's own refusals (O2 short, no H2S, bad reaction set) | `SulfurRecoveryError` | (R0 messages) |

## Params
```yaml
params:
  type: object
  required: [T_thermal, P, T_condenser, thermal_conversion, catalytic_stages, reaction_set]
  additionalProperties: false
  properties:
    T_thermal: {type: number, description: reaction-furnace temperature (K); R0 thermal rule}
    P: {type: number, description: process pressure (Pa abs)}
    T_condenser: {type: number, description: sulfur condenser temperature (K); complete S6+S8 condensation}
    thermal_conversion: {type: number, minimum: 0, maximum: 1, description: Claus conversion of the post-burn SO2 in the furnace (R0 rule)}
    catalytic_stages:
      type: array
      description: one entry per converter; Gibbs equilibrium at T + approach_K (isothermal)
      items:
        type: object
        required: [T]
        additionalProperties: false
        properties:
          T: {type: number, exclusiveMinimum: 0, description: converter temperature (K)}
          approach_K: {type: number, minimum: 0, description: equilibrium approach (K), default 0}
    extra_species:
      type: array
      items: {enum: [COS, CS2, CO, H2]}
      description: species added to every converter's Gibbs set
    reaction_set: {type: object, description: flowsheet-owned set for the thermal stage (H2S burn + Claus), as at R0}
```

## Outputs
- `tail_gas_out` and `sulfur_out` at (T_condenser, P).
- `duty_W` on the formation basis (R0's formula). `power_W` = 0.
- `info` as listed in the Algorithm.

## Tests (numbers from `calc_sulfur_recovery.py`: an independent extent-space solve of 2 H2S + SO2 → 2 H2O + (3/6) S6 and → (3/8) S8 with scipy `fsolve` on ln K, μ° from the data layer)
- **Closed-form Gibbs converter, isothermal:**
  - Feed {H2S 2.0, SO2 1.0, H2O 4.0, N2 10.0} mol/s at P = 1.3e5 Pa, species {H2S, SO2, H2O, S6, S8, N2}.
  - Expected (rel 1e-7):

    | T (K) | H2S | SO2 | H2O | S6 | S8 | H2S conversion |
    |---|---|---|---|---|---|---|
    | 500 | 0.1484047 | 0.0742023499 | 5.8515953 | 0.0510661578 | 0.3088745 | 0.92579765 |
    | 550 | 0.300279162 | 0.150139581 | 5.69972084 | 0.0789358317 | 0.259495783 | 0.849860419 |
    | 600 | 0.524034079 | 0.26201704 | 5.47596592 | 0.103411603 | 0.199184908 | 0.73798296 |

  - ln K at 550 K: S6 route 7.78370127, S8 route 8.86491862.
  - Cross-check: `gibbs_minimum` with N2 as a species reproduces the 550 K row to 9 significant figures (measured).
  - The test calls the internal stage function directly (`_converter_equilibrium(gas, T, P, species)`).
- **R0 identity:** R2's stage at the R0 species set equals R0's approach result (rel 1e-10).
  - Measured while writing this spec: gas {H2S 2.0, SO2 1.0, H2O 4.0, N2 10.0, CO2 1.0}, T 473 K, approach 30 K, P 1.5e5 Pa.
  - R0's `_approach_extent` plus `apply_extents` gives H2S 0.15518331468558655, SO2 0.07759165734279327, H2O 5.844816685314413, S8 0.34590312849645255.
  - `gibbs_minimum(["H2S","SO2","H2O","S8","N2","CO2"], [], gas, 503 K, P)` agrees to ≤ 1.4e-14 relative.
  - So the "1e-6 cross-check" bound in gibbs.py is loose for this case; use 1e-10.
- **Element balance (V0):** S, H, O, N and C atoms in = out at 1e-8, and total mass at 1e-8, on the example case.
- **Direction:** H2S conversion falls as the converter T rises (from the table). Assert strictly decreasing over 500/550/600 K.
- **Refusals:** one per row of the table.
- **V1:** keep R0's GPSA Ex. 22-1 first-converter case.
  - Add an R2 case only if the GPSA EDB Sect. 22 example prints a converter outlet composition at a stated temperature (a stage equilibrium). Transcribe it from the printed page only; the published example's equilibrium basis may differ (an S8-only or chart-based basis), and any miss goes in `assessed`.
  - Otherwise: V1 gap, searching GPSA EDB Sect. 22 and Kohl & Nielsen, *Gas Purification*, 5th ed., ch. 8 (Claus equilibrium tables).

## Steps
1. **`_converter_equilibrium`** (species assembly with the inert workaround and formation-data refusals), the closed-form table test and the direction test (≈35 min). Push and open the PR.
2. **The `SulfurRecoveryR2` adapter:** R0's thermal stage path, the converters loop, the condenser, outlets, duty, info, the R0-identity test and the refusals (≈40 min). Push.
3. **`example_case`** (R0's feeds and params with the `conversion` stage replaced by `{T: 573.0}`), catalogue flip, docs and gates (≈30 min). Row note: "Gibbs equilibrium per catalytic converter (isothermal; S6/S8 ± COS/CS2); furnace = R0 rule (S2 data missing); complete sulfur condensation (package S8 Psat unusable)". Push.

## Review checklist
- All feed species, inerts included, are passed as Gibbs `species` with `inerts=[]`.
- No `conversion` path at R2.
- S6 is carried into `sulfur_out` and into the recovery fraction (6 and 8 atoms).
- The furnace is unchanged from R0.
- There is no adiabatic solve; converters are isothermal by scope (see the module docstring) — a modelling choice, with adiabatic beds as a follow-up.
- Stage T_eq = T + approach_K.
- The species-override keyword stays internal; no public param is added for it.
