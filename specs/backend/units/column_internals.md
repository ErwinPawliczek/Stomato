# column_internals R1: tray and packing hydraulics (flooding, pressure drop) as a pass-through rating unit

- **Family / package:** column, `src/ngdesign/units/column_shortcut/`
- **Levels delivered:** R1, from `planned` to `provisional` (the row's only level, `end_state`)
- **Depends on:** U-R2 conventions, U-01d (#243). No column-package import at all: the unit consumes a stream.
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/column_internals` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/column_shortcut/column_internals_r1.py` (new)
  - `tests/units/column_shortcut/test_column_internals_r1.py` (new)
  - `data/validation_units/column/cases/column_internals.yaml` (new, only if a V1 case lands)
  - `data/unit_models/column.yaml`: only `levels.R1` of row `column_internals`, plus its `notes` line
- **Read-only imports (verified on main, fluids 1.3.1):**
  - `fluids.packed_tower.Stichlmair_flood(Vl, rhog, rhol, mug, voidage, specific_area, C1, C2, C3, H=1.0) -> Vg_flood [m/s]`
  - `fluids.packed_tower.Stichlmair_wet(Vg, Vl, rhog, rhol, mug, voidage, specific_area, C1, C2, C3, H=1.0) -> dP [Pa]`
  - `fluids.packed_tower.Stichlmair_dry(Vg, rhog, mug, voidage, specific_area, C1, C2, C3, H=1.0) -> dP [Pa]`
  - `fluids.packed_tower.Robbins(L, G, rhol, rhog, mul, H=1.0, Fpd=24.0) -> dP [Pa]`, with L and G in kg/s/m² and **Fpd in 1/ft** (the library's unit)
  - `ngdesign.contracts.StreamState`, `UnitResult`, `PhaseKind`; `ngdesign.contracts.plugins.Thermo`
- **Current state:** the row exists with R1 `planned` and no adapter. Ports: inlet `inlet` ("solved column result (hydraulics input)"), outlet `outlet` ("hydraulics report"). Notes: "roadmap; S1 slice". There is no column sizer in `ngdesign.sizing`.

## Method
The unit rates ONE column section from that section's vapour and liquid traffic.
- **Inlet:** a two-phase `StreamState` at the section's (T, P) whose vapour and liquid phases carry the traffic. V = molar_flow·VF and L = molar_flow·(1−VF); densities, viscosities and molecular weights come from the stream's `phases`. A flowsheet builds it from a solved column's stage `V_j`, `L_j`, `x_j`, `y_j` (a later flowsheet helper, out of scope here).
- **Outlet:** the same state, passed through unchanged, so V0 closes exactly with `duty_W = power_W = 0`. All results go in `info`.

### Equations: sieve tray (`internals = "sieve_tray"`)
Seader, Henley & Roper, *Separation Process Principles*, 3rd ed., §6.6 (flooding, diameter, tray pressure drop). Symbols are SI; G and L are mass flows (kg/s).
1. Flow parameter: `F_LV = (L/G)·sqrt(ρV/ρL)`.
2. Capacity parameter, Fair (1961) chart, in the Lygeros & Magoulas (1986) fit (Hydrocarbon Processing 65(12), 43): `C_SB = 0.0105 + 8.127e-4·TS^0.755·exp(−1.463·F_LV^0.842)`, with C_SB in m/s and TS (tray spacing) in **mm**.
   - **The implementer must verify this printed form and its units against the source, or against Kister (*Distillation Design*, 1992), before coding.** If it cannot be verified, `C_SB_m_s` becomes a required user param instead, and the PR says so.
3. Corrections: `C = F_ST·F_F·F_HA·C_SB`.
   - `F_ST = (σ/0.020 N/m)^0.2`;
   - `F_F = foaming_factor` (param, default 1.0 = non-foaming);
   - `F_HA = 1` for `Ah/Aa ≥ 0.10`, and `F_HA = 5·(Ah/Aa) + 0.5` for `0.06 ≤ Ah/Aa < 0.10`. Refuse below 0.06.
4. Flooding velocity on the net area: `U_f = C·sqrt((ρL − ρV)/ρV)`.
5. Rating at a given `diameter_m`:
   - `A_t = π·D²/4`, `A_n = A_t·(1 − Ad/At)`;
   - `U_n = (G/ρV)/A_n`;
   - `flood_fraction = U_n/U_f`.
6. Design mode (if `design_flood_fraction` f is given instead of `diameter_m`): `D = sqrt(4·G / (f·U_f·π·(1 − Ad/At)·ρV))`.
7. Dry-tray head, orifice equation: `h_d = (ρV/ρL)·u_o²/(2·g·C_o²)`.
   - `u_o = (G/ρV)/A_h`, `A_h = (Ah/Aa)·A_a`, `A_a = A_t·(1 − 2·Ad/At)`; C_o is a param.
   - This is the SI form of the book's `h_d = 0.186·(u_o²/C_o²)·(ρV/ρL)` [in, ft/s]: 0.186 in = 1/(2g) in US units.
8. Weir crest, Francis weir: `Q_L = 1.84·L_w·h_ow^1.5` (SI), so `h_ow = (q_L/(1.84·L_w))^(2/3)`, with q_L = L/ρL.
9. Liquid head `h_l = β·(h_w + h_ow)`, with β (aeration factor) a param.
10. Tray pressure drop `ΔP_tray = ρL·g·(h_d + h_l)`.

g = 9.80665 m/s² (CODATA standard gravity).

### Equations: packing (`internals = "packing"`)
Stichlmair, Bravo & Fair (1989), *Gas Sep. Purif.* 3, 19–28, via `fluids.packed_tower`:
- superficial velocities `Vg = (G/ρV)/A_t` and `Vl = (L/ρL)/A_t`;
- dry ΔP `Stichlmair_dry`, irrigated ΔP `Stichlmair_wet`, flood gas velocity `Stichlmair_flood`, and `flood_fraction = Vg/Vg_flood`. The packing constants C1, C2, C3, voidage and specific area are params from the user's packing data.
- Optional Robbins (1991, *Chem. Eng. Prog.* 87(5), 87) ΔP when `Fpd_per_ft` is given, reported alongside.

HETP is NOT computed. No open HETP correlation is cited here with confidence. If the user supplies `hetp_m` and `n_stages`, the packed height is reported as `n_stages·hetp_m`; otherwise it is omitted.

### Algorithm
1. Validate the params against the table. Split the inlet phases: exactly one `VAPOR` phase, and one or more liquid phases pooled (moles add; density by mole-weighted molar volume). Refuse if there is no vapour or no liquid.
2. Mass flows: `G = V·MW_V/1000`, `L = L_mol·MW_L/1000` (kg/s). Viscosities come from the phases and are used only by the packing branch; there, a `None` viscosity is refused (never assumed).
3. Evaluate the tray or packing equations above. There is no iteration except inside the fluids `Stichlmair_flood` solve, which is the library's own; wrap it and convert any exception to `ColumnInternalsError`, naming the inputs.
4. `outlet` = the inlet state itself (passed through). `duty_W = 0`, `power_W = 0`.

### Reduction to the lower level
None: R1 is the first level of this row.

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `internals` not in {`sieve_tray`, `packing`} | `ColumnInternalsError(ValueError)` (new) | `internals` |
| inlet without a vapour phase, or without a liquid phase | `ColumnInternalsError` | `two-phase` |
| packing: the vapour viscosity (or, for Robbins, the liquid viscosity) is `None` | `ColumnInternalsError` | `viscosity` |
| tray: neither or both of `diameter_m` / `design_flood_fraction` | `ColumnInternalsError` | `diameter_m` |
| tray: `hole_area_frac` < 0.06 or > 0.20 | `ColumnInternalsError` | `hole_area_frac` |
| tray: `downcomer_area_frac` not in (0, 0.5) | `ColumnInternalsError` | `downcomer_area_frac` |
| any length, area or density param ≤ 0, `surface_tension_N_m` ≤ 0, `aeration_factor` not in (0, 1] | `ColumnInternalsError` | (param name) |
| packing: `voidage` not in (0, 1) | `ColumnInternalsError` | `voidage` |
| packing: the Stichlmair flood solve fails | `ColumnInternalsError` | `Stichlmair` |

## Params
| name | type | unit | required/default | meaning |
|---|---|---|---|---|
| `internals` | string | — | required | `sieve_tray` or `packing` |
| `surface_tension_N_m` | number | N/m | required (tray) | liquid surface tension; no thermo source in the contract |
| `tray_spacing_m` | number | m | required (tray) | TS |
| `diameter_m` | number | m | tray: one of | rating diameter |
| `design_flood_fraction` | number | — | tray: one of | f for design mode, in (0, 1) |
| `downcomer_area_frac` | number | — | required (tray) | Ad/At |
| `hole_area_frac` | number | — | required (tray) | Ah/Aa |
| `weir_height_m` | number | m | required (tray) | h_w |
| `weir_length_m` | number | m | required (tray) | L_w |
| `orifice_coefficient` | number | — | required (tray) | C_o |
| `aeration_factor` | number | — | required (tray) | β |
| `foaming_factor` | number | — | default 1.0 | F_F |
| `column_diameter_m` | number | m | required (packing) | D |
| `packed_height_m` | number | m | required (packing) | H |
| `voidage` | number | — | required (packing) | ε |
| `specific_area_m2_m3` | number | m²/m³ | required (packing) | a |
| `stichlmair_C1`, `stichlmair_C2`, `stichlmair_C3` | number | — | required (packing) | packing constants |
| `Fpd_per_ft` | number | 1/ft | optional (packing) | Robbins packing factor |
| `hetp_m`, `n_stages` | number, integer | m, — | optional, both or neither | packed height report |

The JSON-schema fragment is these properties with `required: [internals]` and `additionalProperties: false`. The per-internals requirements are enforced in code, through the refusal table.

## Outputs
- `outlet`: the inlet state, passed through. `duty_W = 0`, `power_W = 0`.
- `info` (tray): `F_LV`, `C_SB_m_s`, `C_m_s`, `U_flood_m_s`, `U_net_m_s`, `flood_fraction`, `diameter_m` (input or designed), `A_total_m2`, `A_net_m2`, `A_active_m2`, `A_hole_m2`, `u_hole_m_s`, `h_dry_m`, `h_ow_m`, `h_liquid_m`, `dP_tray_Pa`.
- `info` (packing): `Vg_m_s`, `Vl_m_s`, `Vg_flood_m_s`, `flood_fraction`, `dP_dry_Pa`, `dP_wet_Pa`, `dP_robbins_Pa` (if Fpd is given), `packed_height_from_hetp_m` (if given).

## Tests
- **Closed-form tray** (script `calc_column_internals.py`; plain arithmetic, no fluids):
  - Build the inlet `StreamState` literally, with phases: vapour MW 40 g/mol, 50 mol/s (G = 2.0 kg/s), ρV = 20, μV = 1e-5; liquid MW 80 g/mol, 60 mol/s (L = 4.8 kg/s), ρL = 600, μL = 2e-4.
  - Params: σ = 0.015 N/m, TS = 0.6096 m (609.6 mm), D = 1.5 m, Ad/At = 0.12, Ah/Aa = 0.10, h_w = 0.05 m, L_w = 1.1 m, C_o = 0.73, β = 0.6.
  - Expected (rel 1e-9):

    | quantity | value |
    |---|---|
    | F_LV | 0.438178046 |
    | C_SB | 0.0600980456 m/s |
    | F_ST | 0.944087511 |
    | C | 0.0567378143 m/s |
    | U_f | 0.305542481 m/s |
    | A_t | 1.76714587 m² |
    | A_n | 1.55508836 m² |
    | U_n | 0.0643050275 m/s |
    | flood_fraction | 0.210461823 |
    | A_a | 1.34303086 m² |
    | A_h | 0.134303086 m² |
    | u_o | 0.744584529 m/s |
    | h_d | 0.00176811444 m |
    | q_L | 0.008 m³/s |
    | h_ow | 0.0249988282 m |
    | h_l | 0.0449992969 m |
    | ΔP_tray | 275.178981 Pa |

  - Design mode with f = 0.80 gives D = 0.769365893 m.
- **Closed-form packing (dry ΔP, hand Stichlmair):** ε = 0.68, a = 260 m²/m³, C1/C2/C3 = 32/7/1, ρG = 5 kg/m³, μG = 5e-5 Pa·s, Vg = 1.0 m/s, H = 1 m.
  - d_p = 6(1−ε)/a = 0.00738461538 m; Re = 738.461538; f0 = C1/Re + C2/√Re + C3 = 1.30092636;
  - ΔP_dry = ¾·f0·(1−ε)/ε^4.65·ρG·Vg²/d_p·H = **1270.39751 Pa**. It matches `fluids.Stichlmair_dry` = 1270.397511660357 to 1e-12.
  - The test builds the inlet so that Vg = 1.0 m/s at the chosen D, and asserts `dP_dry_Pa`.
- **Wet ΔP and flood:** assert the library call wiring only: `dP_wet_Pa` equals `Stichlmair_wet` called with the hand-derived superficial velocities (rel 1e-12). The unit conversion is the thing under test.
- **Pass-through:** `outlet == inlet` (all fields), `duty_W == 0`, V0 closes.
- **Refusals:** one per row of the table.
- **V1 candidates:** Seader, Henley & Roper 3rd ed. §6.6 prints a worked sieve-tray flooding and diameter example with inputs and results. I have not verified its numbers. The implementer transcribes it only from the printed page, with page and example number; otherwise this is a V1 gap. Note that the book reads C_F from the Fair chart, so a fit-based C_SB miss goes in `assessed`.

## Steps
1. **Tray branch (≈40 min).** Module, `ColumnInternalsError`, the tray equations, the closed-form tray test, the design-mode test and the tray refusals. Verify the C_SB fit source first; if unverifiable, switch to a required `C_SB_m_s` param and adjust the test. Push and open the PR.
2. **Packing branch (≈35 min).** Stichlmair dry/wet/flood and the Robbins wiring, the dry closed-form test, the wiring tests and the packing refusals. Push.
3. **Catalogue flip, `example_case` (tray rating at the closed-form state), docs and gates (≈30 min).** Push.

## Review checklist
- The C_SB fit: TS in mm, C_SB in m/s, and the source verified (or the param route taken).
- F_ST uses σ/0.020 N/m.
- The h_d SI form has no stray 0.186.
- The Francis constant is 1.84 (SI).
- Robbins `Fpd` is passed in 1/ft, as fluids expects.
- The outlet is passed through unchanged, so there is no hidden flash.
- No defaults beyond `foaming_factor`.
