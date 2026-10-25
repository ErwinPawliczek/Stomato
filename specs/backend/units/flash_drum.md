# flash_drum R1: Souders-Brown sizing and droplet carry-over at a given diameter

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions, U-01d (#243), and **scrubber R1 merged**: this unit imports `scrubber_r1`'s helpers, the single owner of the carry-over method.
- **Wave/order:** after scrubber R1. Same method, so there is no second copy of the helpers.
- **Branch:** `u-lv/flash_drum` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/flash_drum_r1.py` (new): the class `FlashDrumR1` and `FlashDrumR1SpecError`
  - `tests/units/separation/test_flash_drum_r1.py` (new)
  - `data/validation_units/separation/cases/flash_drum.yaml` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `flash_drum`, plus that row's `notes` line
- **Read-only imports (verified, or to be created by scrubber R1):**
  - from `ngdesign.units.separation.scrubber_r1`: `york_K_m_s(P_Pa) -> float`, `size_gas_section(K, rho_l, rho_g, Q_g) -> dict`, `cut_diameter_m(v_g, rho_l, rho_g, mu_g) -> float`, `rosin_rammler_fines(d, d_rr, n) -> float`, `ScrubberR1SpecError`. If the names differ in the merged scrubber PR, use the merged names.
  - `ngdesign.units.separation.flash_drum.FlashDrum` (R0) and `FlashDrumSpecError`; do not edit `flash_drum.py`.
  - `ngdesign.sizing.souders_brown.souders_brown` (through `size_gas_section`).
- **Current state:**
  - R0 is `ngdesign.units.separation.flash_drum:FlashDrum`, with inlets `inlet` and `inlet_2` (optional) → `gas_out`, `liquid_out`, `aqueous_out`.
  - It adiabatically PH-mixes the inlets at the lowest P, then runs a PT/PH(`duty_W`)/PVF(`vapor_fraction`) flash at `outlet_P`.
  - Its outlets come from `_util.phase_outlet`, a per-phase `flash_pt`.
  - `duty_W = Σ n·h out − Σ n·h in`; `info.T_out_K`.

## Method
### Equations
S1–S6 exactly as in `specs/backend/units/scrubber.md` (Souders-Brown, York K, gas velocity at D, Morrison cut diameter, Rosin-Rammler fines, carry-over), applied to the flash drum's outlets. No new equations.

### Algorithm
1. `r0 = FlashDrum().solve(inlets, r0_params, thermo)`, where `r0_params` is the params minus the R1 keys (`K_m_s`, `diameter_m`, `inlet_entrained_fraction`, `droplet_d_rr_m`, `droplet_n_rr`, `gas_viscosity_Pa_s`).
2. Gas properties come from `r0.outlets["gas_out"]`'s vapour phase, as in scrubber step 2.
3. **The liquid is `liquid_out` and `aqueous_out` together.**
   - `ṁ_L = ṁ_liq + ṁ_aq`.
   - `ρ_L` is the mass-weighted volumetric mean over every liquid phase of both outlets.
   - A zero-flow outlet contributes nothing.
4. K, then `size_gas_section`, as in scrubber steps 4–5. The York pressure is `gas_out.P`.
5. With `diameter_m`: compute `v_G`, `d_cut` (`cut_diameter_m`), `F`, then `ṁ_co = E·ṁ_L·F`. The carry-over leaves **each liquid outlet in proportion to its mass**: the molar fraction removed from each is `f = ṁ_co/ṁ_L`, the same f for both.
6. Outlets:
   - `liquid_out` and `aqueous_out` are `model_copy(update={"molar_flow": (1−f)·n})`; no re-flash.
   - `gas_out` is `thermo.flash_pt(z_mix, T_out, P_out, n_G + f·(n_liq + n_aq))`, with `T_out = r0.info["T_out_K"]` and `P_out = gas_out.P`.
   - With `f == 0`, return R0's outlets as they are.
7. `duty_W = Σ n·h(outlets) − Σ n·h(inlets)`, recomputed. `info` is R0's `T_out_K` plus the scrubber's R1 keys.

### Reduction to the lower level
- With no `diameter_m`, or `inlet_entrained_fraction = 0`, the outlets, `duty_W` and `info.T_out_K` equal R0's exactly.
- With carry-over and a `duty_W` spec, the recomputed duty equals R0's duty to relative 1e-8. The redistribution is isothermal and isobaric between coexisting phases; the residual is flash tolerance.

### Refusals (`FlashDrumR1SpecError(ValueError)`)
The same table as scrubber R1. R0's own refusals (`FlashDrumSpecError`) propagate unchanged. Add:
| Condition | Message fragment |
|---|---|
| `diameter_m` given and R0 `gas_out` zero-flow, or all liquid outlets zero-flow | `both a gas and a liquid` |

## Params
R0's three params (`outlet_P`, `duty_W`, `vapor_fraction`, with the same schema) plus the scrubber's R1 keys (`K_m_s`, `diameter_m`, `inlet_entrained_fraction`, `droplet_d_rr_m`, `droplet_n_rr`, `gas_viscosity_Pa_s`) with identical meanings and ranges:

```yaml
type: object
properties:
  outlet_P: {type: number, description: 'outlet pressure, Pa abs; default min inlet P'}
  duty_W: {type: number, description: 'heat added to the drum, W'}
  vapor_fraction: {type: number, minimum: 0, maximum: 1, description: 'molar vapour fraction; PVF flash'}
  K_m_s: {type: number, exclusiveMinimum: 0, description: 'Souders-Brown K, m/s; default York demister fit'}
  diameter_m: {type: number, exclusiveMinimum: 0, description: 'vessel inside diameter, m; enables carry-over'}
  inlet_entrained_fraction: {type: number, minimum: 0, maximum: 1, description: 'fraction of the liquid entering the gravity section as droplets'}
  droplet_d_rr_m: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler characteristic droplet size, m'}
  droplet_n_rr: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler spread parameter'}
  gas_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'gas viscosity override, Pa s'}
```

## Outputs
- **Ports:** `gas_out`, `liquid_out` and `aqueous_out` (step 6).
- **`duty_W`:** recomputed (step 7). **`power_W`:** 0.
- **`info`:**
  - always: `T_out_K`, `K_m_s`, `v_max_m_s`, `D_min_m`, `rho_gas_kg_m3`, `rho_liquid_kg_m3`, `Q_gas_m3_s`;
  - with a diameter: `v_gas_m_s`, `v_ratio`, `d_cut_m`, `fines_fraction`, `carryover_kg_s`, `carryover_mol_fraction`.

## Tests
- **Closed form:** the helper functions are tested in the scrubber PR. Here, add one end-to-end check that carry-over is split across the liquids **by mass**:
  - **Inputs:** a unit test with a fake two-liquid R0 result is not allowed (no mocks of thermo). Use instead the R0 example feeds (slice wet gas with 0.3 % water, 7.0 and 5.0 MPa inlets, `outlet_P` 3.0 MPa) with `duty_W` 5e5, `diameter_m` 0.6, `inlet_entrained_fraction` 0.05, `droplet_d_rr_m` 3e-4, `droplet_n_rr` 2.5.
  - **Assert:**
    - `(n_liq,R0 − n_liq,R1)/n_liq,R0 == (n_aq,R0 − n_aq,R1)/n_aq,R0 == info.carryover_mol_fraction`, to relative 1e-12, whenever the aqueous outlet is non-zero;
    - `info.carryover_kg_s == E·ṁ_L·info.fines_fraction`, to 1e-12 relative, with ṁ_L recomputed in the test from R0's outlets.
- **Identity:**
  - no diameter → outlets `==` R0's, with the same duty and `T_out_K`;
  - `inlet_entrained_fraction = 0` → the same;
  - with carry-over and the `duty_W` spec → `|duty_R1 − 5e5| ≤ 1e-8·5e5`.
- **Balance:** moles at 1e-12, energy at 1e-8, on the case above.
- **Refusals:** one test per row; also check that R0's `FlashDrumSpecError` (both `duty_W` and `vapor_fraction` given) still propagates.
- **V1 candidates:** the same sources as scrubber R1 (a GPSA Sect. 7 vertical separator example, Svrcek-Monnery 1993). Reuse the same printed example only if its feed is a flash-drum case; otherwise record the V1 gap in the row notes, naming the sources searched.

## Steps
1. `FlashDrumR1` adapter: the identity and refusal tests. Flip the catalogue R1 (`adapter: ngdesign.units.separation.flash_drum_r1:FlashDrumR1`, schema, note). Push, then open the PR.
2. The mass-proportional carry-over test and the balance test. Regenerate the docs, then `--audit`. Push.
3. The V1 case or the recorded gap, then the gates and the reply.

## Review checklist
- The helpers are imported from `scrubber_r1`, not copied.
- Carry-over is proportional by mass across both liquid outlets.
- No re-flash of single phases.
- The R0 duty spec is honoured to 1e-8.
- R0 errors propagate unchanged, and R0's module is untouched.
