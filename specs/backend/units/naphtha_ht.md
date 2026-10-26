# naphtha_ht R1: kinetic hydrotreater (model-compound HDS, HDN and saturation kinetics in catalyst beds on the pfr integrator)

- **Family / package:** refining, `src/ngdesign/units/refining/`
- **Levels delivered:** R1 of row `naphtha_ht`, from `planned` to `provisional` (the end state).
- **Depends on:** **pfr R1 merged** (`ngdesign.units.reactors.plug_flow`). Also U-R2 conventions and U-01d.
- **Wave/order:** after pfr R1, in parallel with reformer_cat.
- **Branch:** `u-lv/naphtha_ht` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/refining/hdt_kinetic.py` (new): adapter `NaphthaHydrotreaterR1`.
  - `tests/units/refining/test_naphtha_ht_r1.py` (new).
  - `data/validation_units/refining/cases/naphtha_ht.yaml` (new).
  - The `levels.R1` entry of row `naphtha_ht` in `data/unit_models/refining.yaml`, plus that row's `notes` line.
- **Read-only imports:**
  - `ngdesign.units.reactors.plug_flow.integrate_plug_flow` and `PlugFlowError`. These are the pfr R1 public API; confirm the signature on main.
  - `ngdesign.units.reactors._shared.thermal_outlet` and `z_from`
  - `ngdesign.units._physics.kinetics.apply_extents` and `enthalpy_with_formation`
  - `ngdesign.units.balance.energy_basis`, `stream_enthalpy`, `species_without_formation` and `SENSIBLE_ONLY_FLAG`
  - `ngdesign.units.refining.reactors_hdt._GAS_CIDS` (frozenset {"H2", "H2S", "NH3"}; the single owner of the gas/treated split), plus `AW_SULFUR` and `AW_NITROGEN`
  - `ngdesign.contracts.reactions.ReactionSet`, `Reaction`, `PowerLaw` and `LHHW`
  - `Thermo.flash_ph` and `Thermo.flash_pt`
- **Current state:** R0 `NaphthaHydrotreater` (`reactors_hdt.py`, Fahim E12.2 slate).
  - It mixes `naphtha_in` + `h2_in` and applies declared removal fractions and conversions by mass yield shift.
  - The split: `gas_out` gets H2, H2S and NH3; `treated_out` gets the rest.
  - Duty is on the formation basis (sensible-only with a pseudo present).
  - Ports: `naphtha_in`, `h2_in` → `treated_out`, `gas_out`.

## Method

### Equations
1. **Reaction slate.** The same model compounds and stoichiometry as R0, so it is element-balanced (Fahim, Al-Sahhaf & Elkilani, *Fundamentals of Petroleum Refining*, 2010, E12.2 and scheme (7.1)). Fixed reaction ids:
   - `hds_thiophene`: thiophene + 4 H2 → nC4 + H2S (base thiophene);
   - `hdn_pyridine`: pyridine + 5 H2 → nC5 + NH3 (base pyridine);
   - `olefin_sat`: 1-pentene + H2 → nC5 (base 1-pentene);
   - `arom_sat`: benzene + 3 H2 → cyclohexane (base benzene).
2. **Kinetics per reaction**, supplied as the contract's own `PowerLaw` or `LHHW` JSON with `rate_units` = `"mol/(kg_cat·s)"`. For example, H2S-inhibited HDS of the Satterfield-type LHHW form:
   r = k·y_T·y_H2 / (1 + K_H2S·y_H2S)².
   This is an `LHHW` with driving force [k, {thiophene: 1, H2: 1}], adsorption [{1}, {K_H2S, H2S: 1}] and exponent 2.
   - A reaction omitted from `kinetics` is inactive (rate 0) and is listed in `info` as `inactive_<id>` = 1.
   - Equilibrium-limited `arom_sat` may use the PowerLaw + `equilibrium` form (forward·(1 − Q/K), #245) or an explicit `reverse`; state which and why.
3. **Beds.** Each bed is the pfr integrator over volume V_b = W_b/ρ_b, with rates per kg_cat scaled by ρ_b (pfr equation 3). Then ∫ρ_b·r′ dV = ∫r′ dW exactly.
4. **Feed mixing** (no reaction): n = n_naphtha + n_H2; H = n_naphtha·h_naphtha + n_H2·h_H2 (package enthalpies, J/s); P_mix = min of the two inlet pressures; mixed = `flash_ph(z, P_mix, H/n, n)`.
5. **Heater before bed b** (optional `inlet_T_K`): Q_heat,b = n·[h(z, inlet_T_K, P) − h(state)], from `flash_pt`.

### Algorithm
1. Validate the params. **Refuse pseudo components** in either inlet: the kinetics act on real model compounds, and a pseudo carrier carries no formation enthalpy for the bed closure. The message names issue #222, pseudo elemental characterization. R0 remains the level for pseudo naphtha.
2. Build the `ReactionSet` `naphtha_ht_r1` from equation 1 plus the user's kinetics. The slate is the union of the inlet components and the products.
3. Mix (equation 4).
4. For each bed in order:
   - apply the heater (equation 5) if `inlet_T_K` is given;
   - `integrate_plug_flow(state, rset, thermo, volume_m3=W_b/ρ_b, energy=bed.thermal, bulk_density_kg_m3=ρ_b, reacting_phase="vapor")`;
   - n_out = `apply_extents(...)`;
   - bed outlet = `thermal_outlet(bed_inlet, n_out, bed.thermal, thermo)`, which closes exactly, with Q_bed,b = its duty (0 when adiabatic).
5. **Split** the final effluent as in R0: `gas_out` gets the `_GAS_CIDS` species present; `treated_out` the rest. Flash each with `flash_pt` at the final T and P. An empty `gas_out` is refused, as in R0.
6. **Duty**, as in R0: duty_W = `stream_enthalpy(outlets, basis)` − `stream_enthalpy(inlets, basis)`, with basis = `energy_basis("mass_elements", inlets, outlets, info)`; with no pseudos this is the formation basis.
   - Info: `heater_duty_b<k>_W`, `bed_duty_b<k>_W`, `bed_T_out_b<k>_K`, `T_closure_gap_b<k>_K`, and `split_enthalpy_W` = duty − Σ(heater + bed duties). The last is the enthalpy change of the ideal sharp split.
   - Also every R0 info key, with the same meaning, computed from the R1 extents: `h2_consumed_mol_s`, `h2s_mol_s`, `nh3_mol_s`, `feed_sulfur_wt_pct` and `feed_nitrogen_wt_pct`.

### Reduction to the lower level
One isothermal bed at 620 K and 3.0e6 Pa (R0's default T_out and P_out), with `hds_thiophene` and `hdn_pyridine` given as first-order PowerLaw with k0 = 1.0e4 mol/(kg_cat·s), Ea = 0 and W large enough that k·W/F ≥ 60, and the saturation reactions omitted. R1 then equals R0 with `sulfur_removal_frac` = `nitrogen_removal_frac` = 1, both conversions 0, T_out 620 and P_out 3.0e6. The criterion is 1e-9 relative on the outlet component flows; the residual thiophene and pyridine are about e⁻⁶⁰ of feed. Duty agrees to 1e-6 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| pseudo component in an inlet | `HdtKineticError` (ValueError) | `#222` |
| `beds` empty; `catalyst_mass_kg` ≤ 0; `bed.thermal` not in {adiabatic, isothermal}; `inlet_T_K` ≤ 0 | `HdtKineticError` | the field name |
| `bulk_density_kg_m3` ≤ 0 or missing | `HdtKineticError` | `bulk_density_kg_m3` |
| `kinetics` key not one of the four reaction ids; kinetics not PowerLaw/LHHW; `rate_units` not per kg_cat | `HdtKineticError` | `kinetics` |
| no kinetics given at all | `HdtKineticError` | `at least one` |
| `gas_out` empty | `HdtKineticError` | `gas_out` |
| integration, two-phase or depletion | `PlugFlowError`, from pfr | as in the pfr spec |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| beds | array | — | required | ≥ 1 entry | `[{"catalyst_mass_kg": >0, "inlet_T_K": K (optional), "thermal": "adiabatic" \| "isothermal"}]` |
| bulk_density_kg_m3 | number | kg/m³ | required | > 0 | catalyst bulk density |
| kinetics | object | — | required | keys ⊂ the four reaction ids | `{reaction_id: PowerLaw \| LHHW JSON}`, rates per kg_cat |

```yaml
params:
  type: object
  required: [beds, bulk_density_kg_m3, kinetics]
  properties:
    beds: {type: array, description: "[{catalyst_mass_kg, inlet_T_K (optional heater set point), thermal: adiabatic|isothermal}] in flow order"}
    bulk_density_kg_m3: {type: number, description: catalyst bulk density, kg/m3}
    kinetics: {type: object, description: "{hds_thiophene|hdn_pyridine|olefin_sat|arom_sat: contract PowerLaw or LHHW, rate_units mol/(kg_cat s)}; omitted reactions are inactive"}
```

## Outputs
- Ports `treated_out` and `gas_out`, as in R0.
- `duty_W` is the overall formation-basis closure (heaters + beds + split); `power_W` = 0.
- V0 on `mass_elements` and the formation basis at 1e-8.

## Tests
- **Closed-form, isothermal first-order HDS with mole change** (`calc_naphtha_ht.py`):
  - Case: thiophene + 4H2 → nC4 + H2S with r′ = k_w·y_T, k_w = 0.02 mol/(kg_cat·s), Ea = 0, mole_fraction basis.
  - Feed on `naphtha_in`: thiophene 0.01 + nC7 1.0 mol/s; `h2_in`: H2 5.0 mol/s. Both at 620 K and 3.0e6 Pa. One isothermal bed; ρ_b = 800 kg/m³.
  - Since F_tot = F0 − 3ξ, the closed form is W(X) = [3ξ + (F0 − 3F_T0)·ln(F_T0/(F_T0 − ξ))]/k_w.
  - For X = 0.9: **W = 689.822943 kg**. With that W the outlet must give thiophene 0.001, H2 4.964, nC4 0.009 and H2S 0.009 mol/s.
  - Tolerance 1e-7 relative (rtol 1e-8).
- **Identity:** the R0 reduction above.
- **Adiabatic two-bed V0:** both beds adiabatic, with a heater before bed 2 (`inlet_T_K`) and all four reactions active (test kinetics). V0 closes at 1e-8, bed 1's outlet T is above its inlet T (exothermic), and the info duties sum to `duty_W` − `split_enthalpy_W` to 1e-9 relative.
- **Refusals:** one per refusal-table row. The pseudo refusal uses R0's `hdt_naphtha` pseudo.
- **V1:** no confirmed open, printed worked example of naphtha HDT kinetics with inputs and outlet results. V1 gap: search
  - Fahim et al. 2010, ch. 7 (hydroconversion), for kinetic examples;
  - Ancheyta, *Modeling and Simulation of Catalytic Reactors for Petroleum Refining* (Wiley 2011), hydrotreating chapters (printed tables);
  - Satterfield & Roberts, *AIChE J.* 14 (1968) 159, thiophene HDS kinetics (a source for kinetic parameters, not a V1 result).

  Record the searched list in the row `notes`. Kinetic parameters transcribed from these with page numbers may become an `example_case` default, but never an expected value.

## Steps (each about 40 minutes, each ending in a push)
1. **Slate and mixing.** `hdt_kinetic.py`: `HdtKineticError`, param validation, the pseudo refusal, the reaction-set build (equations 1–2), the mixer (equation 4) and the heater (equation 5). Test: the refusals reachable so far.
2. **Beds and split.** The bed loop on `integrate_plug_flow` with the `thermal_outlet` closure, the R0-identical split, and the duty/info assembly. Tests: the closed-form HDS case and the R0 identity.
3. **Catalogue.** The adiabatic two-bed V0 test, `example_case` (two adiabatic beds, nC7 carrier with all four model compounds, test kinetics labelled as illustrative), YAML `levels.R1`, `cases/naphtha_ht.yaml` (V1 gap), harness write and `--audit`. Open the PR.

## Review checklist (for the orchestrator)
- The stoichiometry is identical to R0's, and the split imports `_GAS_CIDS` (not a copy).
- The kinetics param is the contract's JSON, with no new rate forms invented. Rates are per kg_cat, with V_b = W_b/ρ_b.
- Each bed closes exactly via `thermal_outlet`; the overall duty is R0's definition; `split_enthalpy_W` is reported.
- The pseudo refusal names #222, and R0 is untouched.
- The closed-form W(X) is used as input and X as output (not the reverse echo).
