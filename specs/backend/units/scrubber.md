# scrubber R1: Souders-Brown sizing and droplet carry-over at a given diameter

- **Family / package:** separation, `src/ngdesign/units/separation/`
- **Levels delivered:** R1 (`planned` → `provisional`). R1 is the row's `end_state`.
- **Depends on:** U-R2 conventions, U-01d (#243). No other unit.
- **Wave/order:** parallel-safe. flash_drum R1 imports this unit's helpers, so **flash_drum runs after this PR merges**.
- **Branch:** `u-lv/scrubber` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/separation/scrubber_r1.py` (new): the class `ScrubberR1`, the public helpers below, and `ScrubberR1SpecError`
  - `tests/units/separation/test_scrubber_r1.py` (new)
  - `data/validation_units/separation/cases/scrubber.yaml` (new; U-01d per-unit file)
  - `data/unit_models/separation.yaml`: only `levels.R1` of row `scrubber`, plus that row's `notes` line if a V1 gap is recorded
- **Read-only imports (verified to exist):**
  - `ngdesign.sizing.souders_brown.souders_brown(K_m_s: float, rho_liquid: float, rho_gas: float, gas_flow_m3_s: float) -> dict[str, float]`, returning keys `v_max_m_s` and `min_diameter_m`. This is the single owner of the Souders-Brown equation.
  - `fluids.separator.K_separator_demister_York(P: float, horizontal: bool = False) -> float`: P in Pa, K in m/s. It **silently clamps** P outside 1–5500 psia, so this unit must refuse outside that range before calling it.
  - `fluids.drag.drag_sphere(Re: float, Method: str | None = None) -> float`, always called with `Method="Morrison"`.
  - `ngdesign.units.separator.Scrubber`, the R0 adapter: instantiate it and call `.solve(...)`. Do not edit `separator.py`.
  - `ngdesign.contracts`: `PhaseKind`, `StreamState`, `UnitResult`; `ngdesign.contracts.plugins.Thermo`.
- **Current state:**
  - R0 is `ngdesign.units.separator:Scrubber`: inlet `inlet` → `gas_out`, `liquid_out`.
  - It PT-flashes at `(T_in, P_in − dP)`. The outlets carry the parent flash's phases as they are, with no re-flash (S-24b). `liquid_out` combines both liquids. `duty_W = Σ n·h out − n·h in`.
  - The only parameter is `dP`, which the R0 catalogue row does not declare.

## Method
### Equations (SI)
- **S1 Souders-Brown** (GPSA Engineering Data Book, Sect. 7; Svrcek & Monnery, Chem. Eng. Prog. 89(10):53, 1993):
  - `v_max = K·sqrt((ρ_L − ρ_G)/ρ_G)`
  - `D_min = sqrt(4·Q_G/(π·v_max))`

  Both are computed by `souders_brown(...)`; never re-derive them.
- **S2 York demister K** (Svrcek & Monnery 1993 fit of the Otto H. York curve), with P in psia and K in ft/s, converted by 0.3048 m/ft:
  - 1 ≤ P < 15: `K = 0.1821 + 0.0029·P + 0.0460·ln P`
  - 15 ≤ P ≤ 40: `K = 0.35`
  - 40 < P ≤ 5500: `K = 0.430 − 0.023·ln P`

  Computed by `K_separator_demister_York(P, horizontal=False)`, which already returns m/s.
- **S3 Gas velocity at a given diameter:** `v_G = 4·Q_G/(π·D²)`. Ratio: `r = v_G/v_max`.
- **S4 Cut diameter.** In a vertical gravity section, a droplet of diameter d is carried over when its terminal velocity is below `v_G` (GPSA Sect. 7, gravity settling; Arnold & Stewart, *Surface Production Operations*, Vol. 1, Ch. 4). `d_cut` solves
  - `g(d) = 4·g·d·(ρ_L − ρ_G)/(3·C_D(Re)·ρ_G·v_G²) − 1 = 0`, with `Re = ρ_G·v_G·d/μ_G` and g = 9.80665 m/s²;
  - `C_D` is Morrison (2013): `24/Re + 2.6(Re/5)/(1+(Re/5)^1.52) + 0.411(Re/263000)^−7.94/(1+(Re/263000)^−8) + Re^0.8/461000`, valid for Re < 1e6.
  - `g(d)` increases monotonically in d.
- **S5 Droplet size distribution:** Rosin-Rammler by mass, with the fraction finer than d `F(d) = 1 − exp(−(d/d_RR)^n_RR)` (Rosin & Rammler 1933, as used for separator droplets by Bothamley, "Gas/liquid separators: quantifying separation performance", Oil & Gas Facilities, 2013).
- **S6 Carry-over:** `ṁ_co = E·ṁ_L·F(d_cut)`.
  - `ṁ_L` is the mass flow of R0's `liquid_out`.
  - `E` is `inlet_entrained_fraction`: the fraction of that liquid that reaches the gravity section as droplets dispersed in the gas.

### Algorithm
1. Call the R0 `Scrubber().solve(inlets, {"dP": params.get("dP", 0.0)}, thermo)`. Keep its result `r0`. If `diameter_m` is absent, steps 6–9 are skipped.
2. Gas properties come from the vapour phase of `r0.outlets["gas_out"]`: `ρ_G = phase.density` and `μ_G = phase.viscosity`.
   - If the viscosity is None, use the `gas_viscosity_Pa_s` param, or refuse.
   - `Q_G = gas_out.mass_flow/ρ_G`.
3. Liquid density: `ρ_L = ṁ_L / Σ(ṁ_phase/ρ_phase)` over the liquid phases of `liquid_out`, i.e. the mass-weighted volumetric mean. With `m_phase = mole_fraction·molar_flow·MW/1000`.
4. K: the `K_m_s` param if given. Otherwise the York value at `gas_out.P`, after checking 1 ≤ P/6894.757293168 ≤ 5500 (refuse outside).
5. Call `souders_brown(K, ρ_L, ρ_G, Q_G)` and record `v_max` and `D_min`.
6. With `diameter_m`: compute `v_G` and `r` (S3).
7. Find `d_cut` by bisection on log d over [1e-8, 1e-1] m (S4):
   - stop when `hi/lo − 1 < 1e-12`;
   - cap at 200 iterations, raising `ScrubberR1SpecError("cut diameter did not converge")` at the cap;
   - if `g(1e-1) < 0` (even 10 cm drops are carried), set `F = 1.0` and report `d_cut_m = inf` as the float `math.inf`.
8. `F = F(d_cut)` (S5); `ṁ_co = E·ṁ_L·F` (S6). The molar carry-over fraction of `liquid_out` is `f = ṁ_co/ṁ_L` (same composition).
9. Outlets:
   - `liquid_out` is `r0.outlets["liquid_out"].model_copy(update={"molar_flow": (1−f)·n_L})`. Same intensive state; **never re-flash a single equilibrium phase** (S-24b).
   - `gas_out` is `thermo.flash_pt(z_mix, T, P, n_G + f·n_L)`, where `z_mix` is the flow-weighted composition of gas_out and the carried liquid. This is a genuinely two-phase state, so a flash is valid.
   - With `f == 0`, return R0's outlets unchanged, as the same objects.
10. `duty_W = Σ n·h(outlets) − n_in·h_in`, as in R0. `power_W = 0`.

### Reduction to the lower level
With no `diameter_m`, or `inlet_entrained_fraction = 0`, every outlet equals R0's exactly, and `duty_W` equals R0's to 0 ulp. This is the identity test.

### Refusals (`ScrubberR1SpecError(ValueError)`, defined in the owned module)
| Condition | Message fragment |
|---|---|
| `diameter_m` ≤ 0 | `diameter_m` |
| `K_m_s` ≤ 0 | `K_m_s` |
| `inlet_entrained_fraction` outside [0, 1] | `inlet_entrained_fraction` |
| `diameter_m` given without `inlet_entrained_fraction`, `droplet_d_rr_m` or `droplet_n_rr` | `requires` |
| `droplet_d_rr_m` ≤ 0 or `droplet_n_rr` ≤ 0 | the parameter name |
| R0 gas or liquid outlet has zero flow (sizing needs both phases) | `both a gas and a liquid` |
| no K given and P outside 1–5500 psia | `York` |
| gas viscosity unavailable and no `gas_viscosity_Pa_s` | `gas_viscosity_Pa_s` |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| dP | number | Pa | 0 | ≥ 0 | passed to R0 |
| K_m_s | number | m/s | York value at P | > 0 | Souders-Brown constant |
| diameter_m | number | m | absent = sizing only | > 0 | vessel inside diameter |
| inlet_entrained_fraction | number | – | required with diameter_m | [0, 1] | liquid fraction reaching the gravity section as droplets |
| droplet_d_rr_m | number | m | required with diameter_m | > 0 | Rosin-Rammler characteristic size |
| droplet_n_rr | number | – | required with diameter_m | > 0 | Rosin-Rammler spread |
| gas_viscosity_Pa_s | number | Pa·s | phase viscosity | > 0 | used only when the package gives none |

```yaml
type: object
properties:
  dP: {type: number, minimum: 0, description: 'pressure drop, Pa; default 0 (R0)'}
  K_m_s: {type: number, exclusiveMinimum: 0, description: 'Souders-Brown K, m/s; default York demister fit at the drum pressure'}
  diameter_m: {type: number, exclusiveMinimum: 0, description: 'vessel inside diameter, m; enables the carry-over calculation'}
  inlet_entrained_fraction: {type: number, minimum: 0, maximum: 1, description: 'fraction of the liquid entering the gravity section as droplets'}
  droplet_d_rr_m: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler characteristic droplet size, m'}
  droplet_n_rr: {type: number, exclusiveMinimum: 0, description: 'Rosin-Rammler spread parameter'}
  gas_viscosity_Pa_s: {type: number, exclusiveMinimum: 0, description: 'gas viscosity override, Pa s'}
```

## Outputs
- **Ports:** `gas_out` and `liquid_out`, per algorithm step 9.
- **`duty_W`:** the balance closure, ≈ 0 for dP = 0. **`power_W`:** 0.
- **`info`** (all floats):
  - always: `K_m_s`, `v_max_m_s`, `D_min_m`, `rho_gas_kg_m3`, `rho_liquid_kg_m3`, `Q_gas_m3_s`;
  - with `diameter_m`: `v_gas_m_s`, `v_ratio`, `d_cut_m`, `fines_fraction`, `carryover_kg_s`, `carryover_mol_fraction`.

## Tests
All closed-form numbers come from `scratchpad/unit-specs/calc_scrubber.py` (math only, independent of fluids and ngdesign).

- **CF1 York K**, testing the helper `york_K_m_s(P_Pa)`. The module wraps the fluids call with the range check.
  | P (Pa) | K (m/s) |
  |---|---|
  | 3.447e6 | 0.0874978814 |
  | 2.0e5 (the 0.35 plateau) | 0.10668 |
  | 5.0e4 | 0.0896930418 |

  Tolerance: relative 1e-9.
- **CF2 Souders-Brown sizing**, through the unit's pure function `size_gas_section(K, ρ_L, ρ_G, Q_G)` with K = 0.107, ρ_L = 600, ρ_G = 30, Q = 1.0:
  - `v_max = 0.466402187`, `D_min = 1.65224623`;
  - rtol 1e-9.
- **CF3 cut diameter**, through the public helper `cut_diameter_m(v_G, ρ_L, ρ_G, μ_G)`:
  - inputs: D = 2.0 m, Q = 1.0 m³/s, μ_G = 1.2e-5;
  - `v_G = 0.318309886`, `v_ratio = 0.682479403`;
  - `d_cut = 2.94733012e-4 m`, at Re = 234.541079;
  - rtol 1e-8.
- **CF4 Rosin-Rammler**, through `rosin_rammler_fines(d_cut, 400e-6, 2.5)`: `0.372516998`, rtol 1e-9.
- **CF5 carry-over:** L = 10 kg/s, E = 0.02 → `0.0745033996 kg/s`, rtol 1e-8. Test this through a pure function.
- **Identity:** on the R0 example feed, R1 with no diameter, and R1 with `inlet_entrained_fraction = 0`, both return outlets `==` R0's, with the same `duty_W`.
- **Unit-level balance:** on the R0 example feed with D = 0.5 m, E = 0.05, d_RR = 300e-6, n = 2.5:
  - moles balance at 1e-12, energy at 1e-8;
  - `gas_out.molar_flow > R0 gas_out.molar_flow`.
- **Refusals:** one test per table row.
- **V1 candidates:**
  - GPSA Engineering Data Book, Sect. 7, the vertical gas-liquid separator sizing example. It prints the gas rate, densities and K, and the resulting diameter. Transcribe the printed inputs and the printed diameter; check the SI edition's example number.
  - Svrcek & Monnery 1993 (CEP), the worked vertical separator example.
  - If neither can be verified from an accessible copy: V1 gap. Search the GPSA 13th/14th ed. Sect. 7 example, the Svrcek-Monnery CEP 1993 example, and Arnold & Stewart Vol. 1 Ch. 4.
  - The York-K fluids docstring example (975 psi → 0.08281536 m/s) is a library self-check, **not** a V1 case.

## Steps (each about 40 minutes or less, each ending in a push)
1. **Pure functions:** module skeleton with `york_K_m_s` (range-checked), `size_gas_section`, `cut_diameter_m`, `rosin_rammler_fines` and `ScrubberR1SpecError`, plus CF1–CF5. Push, then open the PR.
2. **Adapter:** `ScrubberR1.solve`, the identity test, the balance test and every refusal test. Flip the catalogue `levels.R1` (`status: provisional`, `adapter: ngdesign.units.separation.scrubber_r1:ScrubberR1`, params schema, note). Regenerate the docs, then `--audit`. Push.
3. **V1:** add the case to `cases/scrubber.yaml`, or record the gap in the row notes. Run the gates, push, and post the item-by-item reply.

## Review checklist
- `souders_brown` is called, not re-derived.
- York is range-checked before the call, so fluids' silent clamping can't happen.
- Morrison is called through `drag_sphere(..., Method="Morrison")`, and the bisection has its cap and a typed error.
- Liquid outlets are scaled with `model_copy`, never re-flashed; gas_out is re-flashed only as a two-phase mix.
- Identity is exact, with no tolerance.
- No `@register`, and no edit to `separator.py` or `sizing/`.
