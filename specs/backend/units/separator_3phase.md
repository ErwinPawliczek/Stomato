# separator_3phase R1: rating at a given vessel geometry (gas capacity, residence, Stokes liquid-liquid settling)

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state` (docs/unit-catalogue-plan.md §2 U-D 2: "sizing, weir/interface levels, residence").
- **Depends on:** U-R2 conventions, U-01d (#243); the merged scrubber R1 (`scrubber_r1.py`) and decanter R1 (`decanter_r1.py`) helpers.
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/separator_3phase_r1.py` (new): `Separator3PhaseR1`, `Separator3PhaseR1SpecError`, the pure helpers below
  - `tests/units/separation/test_separator_3phase_r1.py` (new)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `separator_3phase` (and moving `end_state` from R0 to R1), plus that row's `notes`
- **Read-only imports (verified to exist):**
  - `ngdesign.units.separator.Separator3Phase` (R0): instantiated and solved; `separator.py` is not edited.
  - `ngdesign.units.separation.scrubber_r1`: `size_gas_section` (which calls the single owner `ngdesign.sizing.souders_brown.souders_brown`), `york_K_m_s` (range-checked York fit), `cut_diameter_m` (Morrison-drag terminal-velocity inversion), `liquid_density_kg_m3`.
  - `ngdesign.units.separation.decanter_r1.stokes_velocity` (Stokes' law, single owner).
  - `fluids.geometry.A_partial_circle(D, h)` (circular-segment area) and `fluids.separator.K_separator_demister_York(P, horizontal=True)`.
  - The import contract allows `units → sizing` (the `engineering-independent` contract only forbids `sizing → units`); scrubber R1 already imports `ngdesign.sizing.souders_brown`. No refactor is needed.
- **Current state:** R0 PT-flashes at `(T_in, P_in − dP)` and maps the vapour, hydrocarbon-liquid and aqueous phases of that one flash to `gas_out`, `hc_out`, `water_out` with no re-flash (S-24b). `duty_W` is the closure. `pr` gives on the R0 example feed: gas ρ = 31.44 kg/m³, μ = 1.07e-5 Pa·s; HC liquid ρ = 611.0, μ = 1.31e-4; aqueous ρ = 851.7, μ = 1.00e-3.

## Method
The vessel is rated, not designed: the geometry (D, L, orientation, NLL, NIL) is given and R1 reports how it performs on R0's phase split. Assumptions: the water layer and oil pad both span the effective length (interface-level control; for a weir design NLL is the oil weir crest), plug flow in each layer, droplets enter uniformly over the layer's flow area, no coalescence, no hindered settling.

### Equations (SI)
- **T1 Layer areas, horizontal.** Circular segment below height h in a circle of diameter D (exact geometry; computed by `fluids.geometry.A_partial_circle`):
  `A(h) = R²·acos((R−h)/R) − (R−h)·sqrt(2Rh − h²)`, R = D/2.
  `A_w = A(h_i)`, `A_o = A(h_l) − A(h_i)`, `A_g = πD²/4 − A(h_l)`; layer heights `H_w = h_i`, `H_o = h_l − h_i`, `H_g = D − h_l`.
  **Vertical:** every layer has the full section `A = πD²/4`; same heights, with `H_g = L − h_l`.
- **T2 Residence times:** `t_o = A_o·L_eff/Q_o`, `t_w = A_w·L_eff/Q_w` (horizontal; vertical `t = A·H/Q`). `Q = ṁ/ρ` per R0 outlet.
- **T3 Gas capacity (Souders–Brown; GPSA Engineering Data Book Sect. 7; Svrcek & Monnery, Chem. Eng. Prog. 89(10):53–60, 1993):**
  `v_max = K·sqrt((ρ_L − ρ_G)/ρ_G)` via `size_gas_section` (owner `souders_brown`); `v_G = Q_G/A_g`; report `v_ratio = v_G/v_max`.
  Default K: York demister fit (Svrcek & Monnery 1993), range-checked by `york_K_m_s`; horizontal vessels then take `K_separator_demister_York(P, horizontal=True)` (the fluids implementation applies the 1.25 factor its docstring attributes to Watkins). `ρ_L` is the mass-weighted volumetric mean of both liquids (`liquid_density_kg_m3(hc_out, water_out)`).
- **T4 Gas-section cut diameter (report only).** Vertical: a droplet is carried when its terminal velocity is below `v_G` (GPSA Sect. 7 gravity settling). Horizontal: a droplet entering at the top of the gas space must fall `H_g` while the gas travels `L_eff`, so the required terminal velocity is `v_s = v_G·H_g/L_eff`. In both cases `d_cut,gas = cut_diameter_m(v_s, ρ_L, ρ_G, μ_G)` (scrubber S4: Morrison 2013 drag through `fluids.drag.drag_sphere`), whose root is exactly the drop whose terminal velocity equals `v_s`.
- **T5 Stokes' law** (Stokes, Trans. Camb. Phil. Soc. 9:8, 1851), via `decanter_r1.stokes_velocity`: `u_t = g·d²·|ρ_w − ρ_o|/(18·μ_c)`, g = 9.80665 m/s², μ_c the continuous phase (oil for water-in-oil, water for oil-in-water).
- **T6 Liquid-liquid cut diameter (report).** The droplet that crosses its whole layer in the residence time: `u_t(d_cut)·t = H`, i.e. `d_cut = sqrt((H/t)/u_t(1 m))` with `u_t(1 m) = stokes_velocity(1.0, …)` (Stokes is ∝ d², so this is the exact inversion through the owner). Water-in-oil uses `H_o, t_o, μ_o`; oil-in-water `H_w, t_w, μ_w`. The cut Reynolds number `Re = ρ_c·u_t·d/μ_c` is reported; a cut with Re ≥ 1 is outside Stokes and is reported, not refused (it is a diagnostic).
- **T7 Capture fraction of a droplet of diameter d** (Hazen 1904 ideal settler, applied to the layer's actual cross-section): during `t` the droplet moves `s = u_t·t`.
  - Horizontal, water drops falling through the oil pad onto the interface: `η_wo = [A(min(h_i + s, h_l)) − A(h_i)]/A_o`.
  - Horizontal, oil drops rising through the water layer: `η_ow = [A(h_i) − A(max(h_i − s, 0))]/A_w`.
  - Vertical (uniform section, counter-current plug flow): `η = 1` if `s ≥ H` (i.e. `u_t ≥ Q/A`), else `0`.
- **T8 Carry-over:** the water-outlet fraction leaving with the oil is `f_w = E_w·(1 − η_wo)`; the oil-outlet fraction leaving with the water is `f_o = E_o·(1 − η_ow)`. `E_w` (`E_o`) is the user-given fraction of the water (oil) that enters the oil pad (water layer) as droplets of the given diameter (monodisperse). Mass and mole fractions coincide (same composition).

Gas-side carry-over is **report only** (T3, T4): a defensible split needs an inlet entrainment and a droplet distribution and a rule for dividing carried liquid between oil and water, which the catalogue does not yet cite. Liquid-liquid carry-over (T8) moves material between the outlets.

### Algorithm
1. Validate params (refusal table). `r0 = Separator3Phase().solve(inlets, {"dP": dP}, thermo)`. With no geometry, return R0's outlets and duty unchanged, `info = {}`.
2. With geometry: all three R0 outlets must have flow. ρ_G, μ_G from the vapour phase of `gas_out`; ρ_o, ρ_w via `liquid_density_kg_m3` of each liquid outlet; μ_o, μ_w from each outlet's liquid phase (overrides `oil_viscosity_Pa_s`, `water_viscosity_Pa_s`, `gas_viscosity_Pa_s` used only when the phase gives none). Refuse when ρ_w ≤ ρ_o.
3. T1–T6 → `info`.
4. With droplet params (T5, T7, T8): refuse a given droplet whose Stokes Re ≥ 1.
5. Outlets: an outlet that only donates is R0's `model_copy(update={"molar_flow": (1−f)·n})` (never re-flashed, S-24b); an outlet that receives is `thermo.flash_pt(z_mix, T, P, n_mix)` of its kept part plus the received liquid (two coexisting liquids at the same T, P). With `f_w = f_o = 0` the outlets are R0's objects.
6. `duty_W = Σ n·h(out) − n_in·h_in`, as R0; with no carry-over it is R0's `duty_W`. `power_W = 0`.

### Reduction to R0
No geometry, or geometry without droplet params, or `E_w = E_o = 0`, or full capture (η = 1): every outlet is R0's object and `duty_W` equals R0's exactly. Identity test at 1e-10 (asserted exact).

### Refusals (`Separator3PhaseR1SpecError(ValueError)`)
| Condition | Message fragment |
|---|---|
| `orientation` not horizontal/vertical | `orientation` |
| any geometry key given without all of `diameter_m`, `length_m`, `liquid_level_m`, `interface_level_m` | `requires` |
| a geometry number ≤ 0 | the parameter name |
| `interface_level_m ≥ liquid_level_m` | `interface_level_m` |
| `liquid_level_m ≥ diameter_m` (horizontal) / `≥ length_m` (vertical) | `liquid_level_m` |
| droplet params without geometry | `geometry` |
| a droplet diameter without its entrained fraction, or vice versa | the parameter name |
| entrained fraction outside [0, 1] | the parameter name |
| `K_m_s` ≤ 0 or viscosity override ≤ 0 | the parameter name |
| an R0 outlet with zero flow when rating | `all three` |
| ρ_water ≤ ρ_oil | `denser` |
| no phase viscosity and no override | the override's name |
| given droplet with Stokes Re ≥ 1 | `Stokes` |

## Params
```yaml
type: object
properties:
  dP: {type: number, minimum: 0, description: 'pressure drop, Pa; default 0 (R0)'}
  orientation: {type: string, enum: [horizontal, vertical], description: 'vessel orientation; default horizontal'}
  diameter_m: {type: number, exclusiveMinimum: 0, description: 'vessel inside diameter, m; enables the rating'}
  length_m: {type: number, exclusiveMinimum: 0, description: 'effective (seam-to-seam) length, m; vertical: height above the bottom seam'}
  liquid_level_m: {type: number, exclusiveMinimum: 0, description: 'normal liquid level (NLL; oil weir crest), m above the bottom'}
  interface_level_m: {type: number, exclusiveMinimum: 0, description: 'normal interface level (NIL), m above the bottom'}
  K_m_s: {type: number, exclusiveMinimum: 0, description: 'Souders-Brown K, m/s; default York fit (x1.25 horizontal)'}
  gas_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'used only when the package gives none'}
  oil_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'used only when the package gives none'}
  water_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'used only when the package gives none'}
  water_in_oil_fraction: {type: number, minimum: 0, maximum: 1, description: 'fraction of the water entering the oil pad as droplets'}
  water_droplet_diameter_m: {type: number, exclusiveMinimum: 0, description: 'water droplet diameter in the oil pad, m'}
  oil_in_water_fraction: {type: number, minimum: 0, maximum: 1, description: 'fraction of the oil entering the water layer as droplets'}
  oil_droplet_diameter_m: {type: number, exclusiveMinimum: 0, description: 'oil droplet diameter in the water layer, m'}
```

## Outputs (`info`, floats, units in keys)
With geometry: `K_m_s`, `v_max_m_s`, `v_gas_m_s`, `v_ratio`, `gas_settling_velocity_m_s`, `d_cut_gas_m`, `A_gas_m2`, `A_oil_m2`, `A_water_m2`, `Q_gas_m3_s`, `Q_oil_m3_s`, `Q_water_m3_s`, `rho_gas_kg_m3`, `rho_liquid_kg_m3`, `rho_oil_kg_m3`, `rho_water_kg_m3`, `mu_oil_Pa_s`, `mu_water_Pa_s`, `t_res_oil_s`, `t_res_water_s`, `d_cut_water_in_oil_m`, `Re_cut_water_in_oil`, `d_cut_oil_in_water_m`, `Re_cut_oil_in_water`. With droplets also `eta_water_in_oil`, `carryover_water_to_oil_kg_s`, `eta_oil_in_water`, `carryover_oil_to_water_kg_s`.

## Tests
- **CF (horizontal, hand-computed):** D = 2, L = 6, NLL = 1, NIL = 0.5; Q_o = 0.01, Q_w = 0.005, Q_G = 1 m³/s; ρ_o = 800, ρ_w = 1000, μ_o = 2e-3, μ_w = 1e-3. `A_w = π/3 − √3/4 = 0.614184849`, `A_o = π/6 + √3/4 = 0.956611477`, `A_g = π/2`; `t_o = 573.966886 s`, `t_w = 737.021819 s`; `d_cut,wo = 1.26449611e-4 m`, `d_cut,ow = 7.89052221e-5 m`; with d_w = 100 µm, d_o = 50 µm: `η_wo = 0.610721789`, `η_ow = 0.520665742`; E_w = 0.1, E_o = 0.05 → `f_w = 0.0389278211`, `f_o = 0.0239667129`. rtol 1e-9.
- **CF vertical:** step capture and `t = A·H/Q`.
- **Identity:** no geometry; geometry without droplets; E = 0 → outlets `is` R0's, same duty.
- **Balances:** with carry-over on the R0 example, moles 1e-12, energy 1e-8; hc_out gains water.
- **Refusals:** one per table row (`pytest.raises(Separator3PhaseR1SpecError, match=...)`).
- **V1:** gap. Candidates: Arnold & Stewart, *Surface Production Operations* Vol. 1 (horizontal three-phase example; text not accessible to verify), PetroWiki "Separator sizing" (now redirects to a OnePetro landing page), GPSA Sect. 7 (no accessible copy). The printed inputs of these examples are SG and viscosity in field units, which the unit takes from the thermo package, so a V1 case would also need a feed that reproduces the printed SGs; none was verifiable.

## Steps
1. Pure helpers + CF tests. 2. Adapter, identity, balances, refusals; catalogue `levels.R1`; regenerate docs. 3. V1 gap in notes; gates.
