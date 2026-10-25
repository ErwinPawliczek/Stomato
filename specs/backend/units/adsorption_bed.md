# adsorption_bed R1: Extended-Langmuir equilibrium loading and length of unused bed (LUB) breakthrough

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions and U-01d (#243).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/adsorption_bed` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/adsorption_bed_r1.py` (new): `AdsorptionBedR1`, `AdsorptionBedR1SpecError`, and the pure functions below
  - `tests/units/separation/test_adsorption_bed_r1.py` (new)
  - `data/validation_units/separation/cases/adsorption_bed.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `adsorption_bed`, plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separation.adsorption_bed.AdsorptionBed` (R0) and `AdsorptionBedSpecError`
  - `ngdesign.units.separation._util.stream_molar_mass(composition) -> float` (g/mol)
  - `ngdesign.contracts`; `Thermo`
- **Current state:**
  - R0 takes `removal_fraction` (the spec split to `regen_out`) and per-outlet T and P.
  - It reports `cycle_time_s = capacity_kg_per_kg·bed_mass_kg/adsorbate mass rate`, plus `adsorbate_mass_rate_kg_s`.
  - The example is mol-sieve dehydration of the slice gas: 95 % H2O removal, 0.10 kg/kg, 500 kg.

## Method
### Equations (SI)
Sources:
- Langmuir (1918), and Markham & Benton (1931) for the extended form;
- the LUB method of Collins (1967), as in McCabe-Smith-Harriott, 7th ed., Ch. 25 ("Adsorption: fixed-bed breakthrough, length of unused bed"), and in Geankoplis, 4th ed., §12.3;
- Ruthven, *Principles of Adsorption and Adsorption Processes* (1984), Ch. 2.
- **A1 Extended Langmuir** (competitive), for the adsorbates j listed in `langmuir`, each with saturation capacity q_m,j (mol/kg) and affinity b_j (1/Pa):
  - `q_i* = q_m,i·b_i·p_i/(1 + Σ_j b_j·p_j)`, with `p_i = y_i·P_feed`, the partial pressure from the feed composition;
  - for a single adsorbate it reduces to `q* = q_m·b·p/(1 + b·p)`.
- **A2 Optional temperature dependence:** `b_i(T) = b_i,ref·exp((−ΔH_ads,i/R)·(1/T − 1/T_ref))`, R = 8.314462618, with ΔH_ads < 0 (exothermic). Applied only when `dH_ads_J_mol` and `T_ref_K` are given; otherwise b is taken at the feed T as given.
- **A3 Bed mass:** the `bed_mass_kg` param, or `ρ_b·(π/4)·D²·L`. Exactly one form.
- **A4 Stoichiometric time** for adsorbate i: `t_s,i = q_i*·m_bed/Ṅ_i`, with `Ṅ_i` the adsorbed molar rate, i.e. the `removal_fraction` × feed molar flow of i.
- **A5 LUB breakthrough:** `t_b,i = t_s,i·(1 − LUB/L)`. Without a length L (bed given by mass), LUB must be 0 or absent.
- **A6 Cycle time** = `min_i t_b,i` over the adsorbates with `Ṅ_i > 0`. The first breakthrough limits the cycle.
- **A7 Loading reported in mass units:** `q_i*·MW_i/1000` kg/kg.

### Algorithm
1. `r0 = AdsorptionBed().solve(inlets, r0_params, thermo)`. `r0_params` is R1's params minus the R1 keys (`langmuir`, `bed_density_kg_m3`, `bed_diameter_m`, `bed_length_m`, `lub_m`, `dH_ads_J_mol`, `T_ref_K`). Pass `bed_mass_kg` only if given, and never pass `capacity_kg_per_kg` (R1 replaces it; refuse if it is given).
   The outlets and duty are R0's: **R1 changes no stream**, only the cycle physics.
2. Validate, then compute A1–A6 at the feed T and P.
3. Assemble `info`: R0's `adsorbate_mass_rate_kg_s`, plus `cycle_time_s` (the R1 value), `t_stoich_s_<cid>`, `t_break_s_<cid>`, `q_eq_mol_kg_<cid>`, `q_eq_kg_kg_<cid>`, `bed_mass_kg`, and `limiting_component_index`, the position of the limiting component in the sorted `langmuir` keys.

### Reduction to the lower level
- For a single adsorbate with `lub_m = 0` (or absent) and `bed_mass_kg` given, R1's `cycle_time_s` equals R0's with `capacity_kg_per_kg = q*·MW/1000`. Tolerance: relative 1e-12.
- The outlets are identical (`==`) to R0's for any R1 params.

### Refusals (`AdsorptionBedR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `langmuir` empty, or naming a component not in `removal_fraction` | `langmuir` |
| any q_m ≤ 0 or b ≤ 0 | `langmuir` (with the cid) |
| a `removal_fraction` component with positive removal that has no `langmuir` entry | `langmuir` |
| `capacity_kg_per_kg` given at R1 | `capacity_kg_per_kg` |
| both or neither of `bed_mass_kg` and (`bed_density_kg_m3`, `bed_diameter_m`, `bed_length_m`) | `bed_mass_kg` |
| `lub_m` < 0, `lub_m ≥ bed_length_m`, or `lub_m > 0` without `bed_length_m` | `lub_m` |
| only one of `dH_ads_J_mol` and `T_ref_K` | `T_ref_K` |

## Params
```yaml
type: object
required: [removal_fraction, langmuir]
properties:
  removal_fraction: {type: object, description: 'component id -> fraction of its molar flow taken to the desorbate (R0 split)'}
  langmuir:
    type: object
    description: 'adsorbate id -> {q_max_mol_kg, b_1_Pa}: extended-Langmuir parameters at the feed T (or at T_ref_K with dH_ads_J_mol)'
  bed_mass_kg: {type: number, exclusiveMinimum: 0, description: 'adsorbent mass, kg (or give density, diameter, length)'}
  bed_density_kg_m3: {type: number, exclusiveMinimum: 0, description: 'bed bulk density, kg/m3'}
  bed_diameter_m: {type: number, exclusiveMinimum: 0, description: 'bed diameter, m'}
  bed_length_m: {type: number, exclusiveMinimum: 0, description: 'bed length, m'}
  lub_m: {type: number, minimum: 0, description: 'length of unused bed from a breakthrough test, m; default 0'}
  dH_ads_J_mol: {type: object, description: 'adsorbate id -> heat of adsorption, J/mol (negative)'}
  T_ref_K: {type: number, exclusiveMinimum: 0, description: 'reference T of the langmuir b values, K'}
  product_P: {type: number, description: 'as R0'}
  regen_P: {type: number, description: 'as R0'}
  product_T: {type: number, description: 'as R0'}
  regen_T: {type: number, description: 'as R0'}
```

## Outputs
- **Ports:** R0's outlets, unchanged.
- **`info`:** as in algorithm step 3.

## Tests
Numbers come from `scratchpad/unit-specs/calc_adsorption_bed.py`. The inputs are illustrative test inputs, not data.
- **CF1:** `langmuir_loading` with q_m = 12 mol/kg, b = 5e-3 1/Pa, P = 7e6 and y = 1e-3 → p = 7000 Pa, `q* = 11.6666667 mol/kg`; rtol 1e-9.
- **CF2 (extended):** add CO2 with q_m = 4, b = 1e-5 and y = 0.015 → `q_H2O = 11.3360324`, `q_CO2 = 0.113360324`; rtol 1e-9.
- **CF3:** ρ_b = 700, D = 1.5, L = 4.0 → `m_bed = 4948.00843 kg`. With 1000 mol/s feed and 100 % H2O removal: `t_s = 57726.765 s`. LUB 0.5 m → `t_b = 50510.9194 s`. rtol 1e-9.
- **CF4 (R0 equivalence):** `capacity_kg_per_kg = 0.210178267` (MW_H2O = 18.01528) gives the R0 cycle time `57726.765 s`. The identity test runs R0 and R1 on the same feed and asserts this to 1e-12, using the actual MW from `stream_molar_mass`.
- **Identity:** R1's outlets `==` R0's on the R0 example feed.
- **Refusals:** one test per row.
- **V1 candidates:**
  - McCabe-Smith-Harriott, 7th ed., Ch. 25, the fixed-bed breakthrough example: from breakthrough data to the LUB, then the breakthrough time of a longer bed.
  - Geankoplis, 4th ed., §12.3, Examples 12.3-1 and 12.3-2 (mass-transfer zone and scale-up of a breakthrough curve). Corroborate through the FOSSEE GeankoplisChapter12 transcription.
  - Transcribe the printed inputs, i.e. the LUB or breakthrough data, bed and flow, and the printed breakthrough time. The comparable quantity is `info.t_break_s_<cid>`.
  - If none can be verified: V1 gap naming them.

## Steps
1. Pure functions A1–A6 plus CF1–CF3. Push, then open the PR.
2. The `AdsorptionBedR1` adapter, with the identity (CF4), outlet-identity and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.adsorption_bed_r1:AdsorptionBedR1`). Regenerate the docs, then `--audit`. Push.
3. V1 or the recorded gap, then the gates and the reply.

## Review checklist
- A1 uses partial pressures from the **feed** composition.
- Stoichiometric time uses the **removed** rate, as R0 does.
- The minimum over adsorbates.
- No stream changes from R0.
- The R0 equivalence holds at 1e-12.
- `capacity_kg_per_kg` is refused at R1.
