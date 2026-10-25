# reformer_cat R1: Smith (1959) four-reaction lumped kinetics in adiabatic beds with interheaters (pfr integrator)

- **Family / package:** refining, `src/ngdesign/units/refining/`
- **Levels delivered:** R1 of row `reformer_cat`, from `planned` to `provisional` (the end state).
- **Depends on:** **pfr R1 merged** (`ngdesign.units.reactors.plug_flow`). Also U-R2 conventions and U-01d.
- **Wave/order:** after pfr R1, in parallel with naphtha_ht.
- **Branch:** `u-lv/reformer_cat` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/refining/reformer_kinetic.py` (new): adapter `CatalyticReformerR1`.
  - `tests/units/refining/test_reformer_cat_r1.py` (new).
  - `data/validation_units/refining/cases/reformer_cat.yaml` (new).
  - The `levels.R1` entry of row `reformer_cat` in `data/unit_models/refining.yaml`, plus that row's `notes` line.
- **Read-only imports:**
  - `ngdesign.units.reactors.plug_flow.integrate_plug_flow` and `PlugFlowError` (the pfr R1 public API; confirm the signature on main)
  - `ngdesign.units.reactors._shared.thermal_outlet` and `z_from`
  - `ngdesign.units._physics.kinetics.apply_extents`, `enthalpy_with_formation` and `R`
  - `ngdesign.units.balance.energy_basis` and `stream_enthalpy`
  - `ngdesign.contracts.reactions.ReactionSet`, `Reaction`, `PowerLaw` and `PowerLawRate`
  - `Thermo.flash_pt`
  - Databank ids, verified to exist with formulas and formation data: `nC7` (C7H16), `methylcyclohexane` (C7H14), `toluene` (C7H8), `H2`, and the curated `C1`, `C2`, `C3`, `nC4`, `nC5`.
- **Current state:** R0 `CatalyticReformer` (`reactors_reformer.py`). Fahim Table 5.3 mass yields against reformate RON, over mass-only pseudo lumps (`reformate`, `reformer_offgas`), with a sensible-only duty. The lumps lack elemental characterization (issue #222). Ports: `naphtha_in` → `reformate_out`, `h2_out`.

## Method

### Equations
1. **Lumps as representative real C7 species**, so that every reaction is element-balanced and the row's `mass_elements` V0 holds with a real heat of reaction: P = `nC7`, N = `methylcyclohexane`, A = `toluene`. The light ends, Smith's C1–C5 lump split equally on a molar basis, are `C1`, `C2`, `C3`, `nC4` and `nC5`.
2. **Reactions** (Smith, *Chem. Eng. Prog.* 55(6) (1959) 76–80, with n = 7):
   - `dehydro`: N ⇌ A + 3 H2 (base N);
   - `n_to_p`: N + H2 ⇌ P (base N);
   - `hc_n`: N + (n/3) H2 → (n/15)(C1 + C2 + C3 + nC4 + nC5) (base N);
   - `hc_p`: P + ((n−3)/3) H2 → (n/15)(C1 + … + nC5) (base P).

   With n = 7 the coefficients are 7/3 and 4/3 H2, and 7/15 per light end. Element balance checked: C 7 = 7/15·15; for `hc_p`, H 16 + 8/3 = 7/15·40 = 18.667.
3. **Smith rate forms**, per catalyst mass, in partial pressures (atm):
   - r1 = k1·(p_N − p_A·p_H³/K1);
   - r2 = k2·(p_N·p_H − p_P/K2);
   - r3 = k3·p_N/P;
   - r4 = k4·p_P/P.
4. **Mapping to the contract.** Every rate becomes a `PowerLaw` on the `mole_fraction` basis with `rate_units` `"mol/(kg_cat·s)"`, using p_i = y_i·P_atm with P_atm = P/101325 for the isobaric bed pressure.
   - Forward and reverse: k0′ = k0·C_u·P_atm^{Σorders}, where C_u = 1000/3600 converts lb-mol/(h·lb_cat) to mol/(kg_cat·s).
   - The equilibrium term is an explicit `reverse` PowerLawRate. If K = exp(A_K − B_K/T), then k/K = (k0·e^{−A_K})·exp(−(Ea − R·B_K)/(R·T)), so the reverse has k0_rev′ = k0·C_u·e^{−A_K}·P_atm^{Σ reverse orders} (for `dehydro` the reverse orders are A 1 + H2 3, so 4) and Ea_rev = Ea − R·B_K.
   - For `hc_n` and `hc_p`, p_i/P = y_i, so the pressure cancels: k0′ = k0·C_u, with mole-fraction order 1 and k0 in lb-mol/(h·lb_cat) with no atm power.
   - Smith's temperatures are in °R: an exponent b/T_R becomes (b/1.8)/T_K, so Ea = R·b/1.8.

   Every unit conversion goes in one function, `_smith_to_contract(...)`, with each factor commented.
5. **Beds.** A sequence of adiabatic beds. Before each bed, a fired interheater sets `inlet_T_K`, with duty n·[h(inlet_T_K) − h(state)] at constant P and composition. Within a bed: the pfr integrator, energy `"adiabatic"` (or `"isothermal"` for tests), V_b = W_b/ρ_b. The pressure is constant per bed; R1 has no ΔP.

### Algorithm
1. Validate. The feed may contain only `nC7`, `methylcyclohexane`, `toluene`, `H2` and `C1`–`nC5`; anything else, a pseudo in particular, is refused with a message naming #222 and pointing to R0. A recycle-hydrogen stream must be mixed upstream, because the row has one feed port.
2. **Kinetics source:**
   - `kinetics: "smith1959"` is a preset, **allowed only once the implementer has transcribed Smith's k_i and K_i constants from the 1959 paper**, or from a reproduction that prints them, with page numbers in the module docstring;
   - otherwise `kinetics` must be the explicit object `{dehydro: {k0, Ea, A_K, B_K}, n_to_p: {k0, Ea, A_K, B_K}, hc_n: {k0, Ea}, hc_p: {k0, Ea}}`, in SI with T in K. Here k0 is in mol/(kg_cat·s·atm^order); the conversion to mole fractions happens in `_smith_to_contract`.
3. Build the `ReactionSet` `reformer_smith_r1` (equations 2–4) at each bed's pressure.
4. For each bed: the interheater, then `integrate_plug_flow(..., volume_m3=W_b/ρ_b, energy=bed.thermal, bulk_density_kg_m3=ρ_b)`, then `apply_extents`, then the exact closure `thermal_outlet(bed_inlet, n_out, bed.thermal, thermo)`.
5. **Split.** `h2_out` gets {H2, C1, C2, C3, nC4}; `reformate_out` gets {nC5, nC7, methylcyclohexane, toluene}. Each is flashed at the last bed's outlet T and P. This is a sharp, idealized product separator, documented, like R0's offgas split.
6. **Duty and info.** duty_W = `stream_enthalpy(outlets, formation)` − `stream_enthalpy(inlets, formation)`.
   - Info: `heater_duty_b<k>_W`, `bed_dT_b<k>_K` (negative: reforming is endothermic), `bed_T_out_b<k>_K`, `split_enthalpy_W`, `extent_<id>_b<k>_mol_s`, `h2_yield_wt_pct`, `aromatics_out_mol_frac_C6plus`, and `T_closure_gap_b<k>_K`.

### Reduction to the lower level
R1 is a different model from R0 (kinetics against a yield correlation), so there is no parameter limit that reproduces R0's yields. Say so in the PR body. The R1 identity is instead: with all k0 = 0, each bed outlet is its inlet, the products are the feed's sharp split at the last `inlet_T_K`, and the duty equals the sum of the heater duties plus `split_enthalpy_W`, to 1e-9 relative.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| feed species outside the slate (pseudo or other) | `ReformerKineticError` (ValueError) | `#222` / `slate` |
| `beds` empty; `catalyst_mass_kg` ≤ 0; `inlet_T_K` ≤ 0; `thermal` not in {adiabatic, isothermal} | `ReformerKineticError` | the field name |
| `bulk_density_kg_m3` ≤ 0 | `ReformerKineticError` | `bulk_density_kg_m3` |
| `kinetics` = "smith1959" before the preset is transcribed with a citation | `ReformerKineticError` | `preset` |
| explicit kinetics missing a reaction or a field | `ReformerKineticError` | the reaction id or field |
| no H2 in the feed while `hc_n`/`hc_p`/`n_to_p` are active: the H2 depletion event | `PlugFlowError`, from pfr | `depletes` |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| beds | array | — | required | ≥ 1 | `[{"catalyst_mass_kg": >0, "inlet_T_K": >0, "thermal": "adiabatic" (default) \| "isothermal"}]` |
| bulk_density_kg_m3 | number | kg/m³ | required | > 0 | catalyst bulk density |
| kinetics | str/object | — | required | `"smith1959"` or the explicit object | Smith-form constants |

```yaml
params:
  type: object
  required: [beds, bulk_density_kg_m3, kinetics]
  properties:
    beds: {type: array, description: "[{catalyst_mass_kg, inlet_T_K (interheater set point), thermal: adiabatic|isothermal}] in flow order"}
    bulk_density_kg_m3: {type: number, description: catalyst bulk density, kg/m3}
    kinetics: {description: "'smith1959' (once transcribed with citation) or {dehydro|n_to_p: {k0, Ea, A_K, B_K}, hc_n|hc_p: {k0, Ea}}; k0 in mol/(kg_cat s atm^order), Ea J/mol, K = exp(A_K - B_K/T[K])"}
```

## Outputs
- Ports `reformate_out` and `h2_out`.
- `duty_W` = heaters + isothermal beds + split; adiabatic beds contribute 0. `power_W` = 0.
- V0 on `mass_elements` and the **formation** basis at 1e-8 (all real species).

## Tests
- **Closed-form equilibrium of `dehydro`** (`calc_reformer_cat.py`):
  - Case: only `dehydro` active (the other three k0 = 0), test constants K1 = exp(46.15 − 25000/T) atm³ (test values, **not Smith's**), forward k0 large enough to equilibrate, one isothermal bed at 650 K and P = 20 atm (2026500 Pa).
  - Feed: MCH 1.0 + H2 5.0 mol/s.
  - The equilibrium y_A·y_H³·P_atm³/y_N = K1 solves independently to K1 = 2183.0135, **ξ_eq = 0.303678901 mol/s**, y_MCH = 0.100754942, y_tol = 0.0439411501 and y_H2 = 0.855303908.
  - Assert the outlet extent to 1e-6 relative. The approach is set by k0·W; pick W so that the remaining driving force is < 1e-9, and state the measured margin.
- **Closed-form conversion check of `_smith_to_contract`:** a unit test on the function alone. With k0 = 1 lb-mol/(h·lb_cat·atm), order 1 and P = 10 atm, k0′ = 1·(1000/3600)·10 = 2.77777778 mol/(kg_cat·s). With b = 18000 °R, Ea = R·18000/1.8 = 83144.6262 J/mol.
- **Identity:** all k0 = 0 (above).
- **Three-bed adiabatic V0:** three adiabatic beds with interheaters to 770 K, all reactions active (test constants). V0 closes at 1e-8, every `bed_dT` < 0, and the total heater duty > 0.
- **Refusals:** one per refusal-table row.
- **V1:**
  - Smith 1959 compares the model with commercial reformer data. If its printed tables give the feed PNA, the catalyst amounts, the temperatures and the product yields, that is the V1 case, with the preset constants.
  - Also search Rase, *Chemical Reactor Design for Process Plants*, vol. 2 (1977), the catalytic-reforming case study, which prints a worked Smith-model calculation.
  - Confirm the page and the printed numbers before use. Otherwise ship a V1 gap naming both sources.

## Steps (each about 40 minutes, each ending in a push)
1. **Conversion and slate.** `reformer_kinetic.py`: `ReformerKineticError`, slate validation, `_smith_to_contract` (equation 4), and the reaction-set build (equations 2–3) with element-balance validation by the contract. Tests: the conversion unit test and the refusals for slate and kinetics.
2. **Beds.** Interheater plus bed loop on `integrate_plug_flow`, the exact closures, the split and the duty/info. Tests: the `dehydro` equilibrium closed form, the k0 = 0 identity and the three-bed V0.
3. **Catalogue.** `example_case` (MCH/nC7/toluene feed with H2, three beds, test kinetics labelled illustrative unless the preset is transcribed), YAML `levels.R1`, `cases/reformer_cat.yaml` (V1 or gap), harness write and `--audit`. Open the PR.

## Review checklist (for the orchestrator)
- The species mapping and the element balance of `hc_n`/`hc_p` are as written. The contract validator accepts them non-lumped.
- Every unit conversion is in `_smith_to_contract` with comments (lb-mol/(h·lb) → mol/(kg·s) is ×1000/3600; atm folding by P_atm^{order}; °R exponents ÷1.8). The reverse rate derives from K, not as an equilibrium flag.
- The preset is gated on a cited transcription; the test constants are labelled as not Smith's.
- No identity with R0 is claimed; the k0 = 0 identity is present.
- Interheater duties are counted; `split_enthalpy_W` is reported.
