# Shell-and-tube exchanger (`shell_tube`)

Family: **heat** · P&ID symbol: `E`

Rigour ladder: R0 provisional, R1 provisional, R2 planned

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
| R2 | planned | — | zoned (phase change), multi-pass with temperature cross |

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

## References

- docs/unit-catalogue-plan.md §2 U-C 2

> The R0 row shares the HeatExchanger adapter. R1 V1 gap - searched Kern 1950 Examples 7.3-7.4 and the Kakaç et al. 3rd ed. Ch. 8 Kern-method worked examples for a complete printed input-and-result set (film coefficients, U and pressure drops with printed inputs); only OCR'd full-text scans are available and no set was verifiable to the U-R1 transcription standard within the time box, so no R1 V1 case is recorded - the closed-form tests and the R1-to-R0 and e-NTU identities carry R1 verification.
