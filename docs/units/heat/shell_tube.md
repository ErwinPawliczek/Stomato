# Shell-and-tube exchanger (`shell_tube`)

Family: **heat** · P&ID symbol: `E`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed |
| outlet | `outlet` | yes | exchanger outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat_exchange:HeatExchanger` | approach / duty with LMTD-F specification |
| R1 | provisional | `ngdesign.units.heat.shell_tube_r1:ShellTubeR1` | rating — Kern shell side (S1-S3) with D_e per layout, duct tube side with 4Ntp return heads, e-NTU S&T, F reported |
| R2 | provisional | `ngdesign.units.heat.shell_tube_r2:ShellTubeR2` | zone analysis with phase change (Nusselt bank on the shell, Shah and Liu-Winterton in the tubes), one F from the terminal temperatures for multi-pass, F_min refusal naming the shells required; shell-side boiling is refused; reduces to R1 in one single-phase zone |

Sizer plugin: `shell_tube`

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K
    type: number
  dP:
    description: pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  R_f_shell_m2K_W:
    description: shell-side fouling, m2 K/W, default 0
    type: number
  R_f_tube_m2K_W:
    description: tube-side fouling, m2 K/W, default 0
    type: number
  allow_extrapolation:
    description: permit Kern outside 2e3 < Re_s < 1e6, flagged in info
    type: boolean
  baffle_spacing_m:
    description: baffle spacing B, m
    type: number
  k_wall_W_mK:
    description: tube wall conductivity, W/(m K), default 45
    type: number
  layout:
    description: tube layout
    enum:
    - triangular30
    - square90
    type: string
  n_baffles:
    description: baffle count Nb
    type: integer
  n_shells:
    description: TEMA E shells in series, default 1
    type: integer
  n_tubes:
    description: total tube count Nt
    type: integer
  pitch_m:
    description: tube pitch PT, m
    type: number
  process_side:
    description: side the process stream flows on
    enum:
    - tube
    - shell
    type: string
  roughness_m:
    description: tube roughness, m, default 4.5e-5
    type: number
  shell_ID_m:
    description: shell inside diameter Ds, m
    type: number
  tube_ID_m:
    description: tube inside diameter, m
    type: number
  tube_OD_m:
    description: tube outside diameter, m
    type: number
  tube_length_m:
    description: tube length per pass, m
    type: number
  tube_passes:
    description: tube passes per shell Ntp
    enum:
    - 1
    - 2
    - 4
    - 6
    - 8
    type: integer
  utility_P_Pa:
    description: utility inlet pressure, Pa
    type: number
  utility_T_K:
    description: utility inlet temperature, K
    type: number
  utility_composition:
    description: utility stream mole fractions
    type: object
  utility_molar_flow:
    description: utility inlet molar flow, mol/s
    type: number
required:
- process_side
- shell_ID_m
- n_tubes
- tube_OD_m
- tube_ID_m
- tube_length_m
- pitch_m
- layout
- baffle_spacing_m
- n_baffles
- tube_passes
- utility_composition
- utility_T_K
- utility_P_Pa
- utility_molar_flow
type: object
```

### R2 parameters

```yaml
properties:
  F_min:
    description: minimum acceptable F, default 0.75
    type: number
  R_f_shell_m2K_W:
    description: shell-side fouling, m2 K/W, default 0
    type: number
  R_f_tube_m2K_W:
    description: tube-side fouling, m2 K/W, default 0
    type: number
  baffle_spacing_m:
    description: baffle spacing, m
    type: number
  k_wall_W_mK:
    description: tube wall conductivity, W/(m K), default 45
    type: number
  layout:
    description: tube layout
    enum:
    - triangular30
    - square90
    type: string
  n_baffles:
    description: baffle count
    type: integer
  n_shells:
    description: TEMA E shells in series, default 1
    type: integer
  n_tubes:
    description: total tube count
    type: integer
  n_zones:
    description: equal-duty zones, 1-200, default 20
    type: integer
  pitch_m:
    description: tube pitch, m
    type: number
  process_side:
    description: side the process stream flows on
    enum:
    - tube
    - shell
    type: string
  roughness_m:
    description: tube roughness, m, default 4.5e-5
    type: number
  shell_ID_m:
    description: shell inside diameter, m
    type: number
  tube_ID_m:
    description: tube inside diameter, m
    type: number
  tube_OD_m:
    description: tube outside diameter, m
    type: number
  tube_length_m:
    description: tube length per pass, m
    type: number
  tube_passes:
    description: tube passes per shell
    enum:
    - 1
    - 2
    - 4
    - 6
    - 8
    type: integer
  tube_rows_vertical:
    description: mean tubes in a vertical row; required for shell-side condensation
    type: integer
  utility_P_Pa:
    description: utility inlet pressure, Pa
    type: number
  utility_T_K:
    description: utility inlet temperature, K
    type: number
  utility_composition:
    description: utility mole fractions
    type: object
  utility_molar_flow:
    description: utility flow, mol/s
    type: number
required:
- process_side
- shell_ID_m
- n_tubes
- tube_OD_m
- tube_ID_m
- tube_length_m
- pitch_m
- layout
- baffle_spacing_m
- n_baffles
- tube_passes
- utility_composition
- utility_T_K
- utility_P_Pa
- utility_molar_flow
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-shell-tube-kern-ex7-4` | R1 | `info.h_shell_W_m2K` | 5735.1 | 5842.74 | abs 2.84 | assessed miss |
| `V1-shell-tube-kern-ex7-4` | R1 | `info.U_W_m2K` | 3049.2 | 3610.93 | abs 2.84 | assessed miss |
| `V1-shell-tube-kern-ex7-4` | R1 | `info.dP_shell_Pa` | 53089.6 | 54850.1 | abs 344.7 | assessed miss |
| `V1-shell-tube-kern-ex7-4` | R1 | `info.dP_tube_Pa` | 51710.7 | 52456.2 | abs 344.7 | assessed miss |

- `V1-shell-tube-kern-ex7-4`: Kern, D.Q., Process Heat Transfer, McGraw-Hill 1950, Example 7.4 "Calculation of a Distilled-water-Raw-water Exchanger", pp. 155-158 (archive.org OCR text https://archive.org/download/KERNProcessHeatTransfer/KERN%20-%20Process%20Heat%20Transfer_djvu.txt, read 2026-11-04): 175,000 lb/hr distilled water 93 -> 85 F in the shell, 280,000 lb/hr raw water from 75 F in the tubes; 15 1/4 in. ID shell, 160 tubes 3/4 in. OD 18 BWG (a't = 0.334 in2, ID 0.652 in), 16 ft, 15/16 in. triangular pitch, two tube passes, baffles 12 in.; printed shell side De = 0.0458 ft, Re_s = 16,200, ho = 1010; tube side Re_t = 36,400, hi = 1335, hio = 1155; clean Uc = 537 Btu/hr ft2 F; dPs = 7.7 psi, dPt = 4.9 + 2.6 = 7.5 psi. SI: ho = 5735.1 W/m2K, Uc = 3049.2 W/m2K, 7.7 psi = 53,089.6 Pa, 7.5 psi = 51,710.7 Pa. Flows 22.0499 and 35.2798 kg/s (1223.97 / 1958.35 mol/s); 15 baffles (Kern's N + 1 = 12 L/B = 16 crossings); both streams at 3 bar (not printed; liquid water, pressure-insensitive); the pr-free-water package carries the IAPWS liquid density and cp and a liquid viscosity (plain PR gives 844 kg/m3 for liquid water). No fouling and k_wall = 1e6 W/m K so the reported U is Kern's clean Uc (1/Uc = 1/hio + 1/ho, no wall term). Tolerances: the printed integer Btu values (+/-0.5 = +/-2.84 W/m2K) and 0.1 psi (+/-344.7 Pa), fixed before the run.
  - assessed: Measured h_shell 5842.7 W/m2K (+1.9% on ho = 1010 -> 5735.1), dP_shell 54,850 Pa (+3.3% on 7.7 psi), dP_tube 52,456 Pa (+1.4% on 7.5 psi), Re_shell 16,366 (Kern 16,200) and Re_tube 38,882 (Kern 36,400 at his 77.5 F viscosity) - the Kern shell-side method and the 4Ntp return-head tube dP track the book within the chart-reading and property spread (Kern reads mu, k from Fig. 14/Table 4 at the caloric temperatures), but not within the printed integer rounding. The clean U misses by +18.4% (3610.9 vs 3049.2 W/m2K): the unit's tube-side h_i = 10,874 W/m2K (ID basis; Gnielinski duct correlation) against Kern's 1335 x 5.678 = 7580 W/m2K read from his water chart (Fig. 25, Eagle & Ferguson 1930), a dimensional water correlation ~30% below Gnielinski at Re 3.9e4. A correlation-choice difference (Kern's chart vs the Gnielinski tube side the level declares), not a coding error; R1 stays provisional.

## References

- docs/unit-catalogue-plan.md §2 U-C 2

> R2 ships provisional on the Nusselt bank closed form and the one-zone reduction to R1 at 1 and 2 passes; the Kern ch. 12 condenser example was not consulted, so no R2 V1 case exists. The R0 row shares the HeatExchanger adapter. R1 V1 gap - searched Kern 1950 Examples 7.3-7.4 and the Kakaç et al. 3rd ed. Ch. 8 Kern-method worked examples for a complete printed input-and-result set (film coefficients, U and pressure drops with printed inputs); only OCR'd full-text scans are available and no set was verifiable to the U-R1 transcription standard within the time box, so no R1 V1 case is recorded - the closed-form tests and the R1-to-R0 and e-NTU identities carry R1 verification.
