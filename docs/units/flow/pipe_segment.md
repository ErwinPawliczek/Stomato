# Pipe segment (`pipe_segment`)

Family: **flow** · P&ID symbol: `PIPE`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | segment inlet |
| outlet | `outlet` | yes | segment outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.pipe_segment:PipeSegment` | fixed ΔP spec; in dP mode an elevation rise subtracts rho*g*z from the outlet pressure, in P_out mode it is reported only |
| R1 | provisional | `ngdesign.units.flow.pipe_segment_r1:PipeSegmentR1` | single-phase Darcy-Colebrook march with elevation (Heun predictor-corrector, refined to 1e-6 of dP); fittings K at the inlet; refuses a two-phase node |
| R2 | provisional | `ngdesign.units.flow.pipe_segment_r2:PipeSegmentR2` | two-phase Beggs-Brill profile (no Payne correction) at a fixed N with the N/2 discretisation check; single-phase segments use the R1 Darcy step, so a line can flash part-way |

### R1 parameters

```yaml
properties:
  D_m:
    description: internal diameter, m
    type: number
  K_fittings:
    description: sum of fitting resistance coefficients
    type: number
  L_m:
    description: length, m
    type: number
  elevation_m:
    description: outlet minus inlet elevation, m
    type: number
  mu_Pa_s:
    description: viscosity override, Pa.s
    type: number
  n_segments:
    description: starting segment count, default 10
    type: integer
  roughness_m:
    description: absolute roughness, m, default 4.57e-5
    type: number
required:
- L_m
- D_m
type: object
```

### R2 parameters

```yaml
properties:
  D_m:
    description: internal diameter, m
    type: number
  K_fittings:
    description: sum of fitting resistance coefficients
    type: number
  L_m:
    description: length, m
    type: number
  elevation_m:
    description: outlet minus inlet elevation, m
    type: number
  mu_Pa_s:
    description: viscosity override, Pa.s
    type: number
  n_segments:
    description: segment count, default 20 (max 200)
    type: integer
  roughness_m:
    description: absolute roughness, m, default 4.57e-5
    type: number
  sigma_N_m:
    description: surface tension, N/m; required if any node is two-phase
    type: number
required:
- L_m
- D_m
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-pipe-segment-gpsa-17-1` | R1 | `info.dP_total_Pa` | 2909.6 | 2868.91 | rel 0.0012 | assessed miss |

- `V1-pipe-segment-gpsa-17-1`: GPSA Engineering Data Book, 13th ed. (FPS), Section 17 Fluid Flow and Piping, Example 17-1, transcribed from the publisher's official calculation workbook (https://www.gpamidstream.org/wp-content/uploads/2025/08/DBCalculations-13thEdition-Section17.xlsx, sheet "Example 17-1", retrieved 2026-11-04): pressure drop in a 10-in. Schedule 40 pipe for 150,000 lb/hr of methane at 60 degF and 750 psia, Z = 0.905 (Fig. 23-5), clean steel pipe; rho = 2.38 lb/ft3; C1 = 22.5 (Fig. 17-8), C2 = 0.0447 (Fig. 17-9); Eq. 17-31 dP100 = C1 C2 / rho = 0.422 psi/100 ft (cell display 0.000). Encoded as 100 ft (30.48 m) of horizontal pipe at the ASME B36.10 10 in. Sch 40 ID 254.46 mm (data/pipe_schedules_b3610.csv) with the unit's default commercial-steel roughness; 150,000 lb/hr = 18.8997 kg/s = 1178.06 mol/s methane; the density and viscosity come from the PR package (the HEOS and GERG packages report no phase viscosity), not the chart Z. 0.422 psi = 2909.6 Pa.
  - assessed: Measured dP_total 2868.9 Pa = 0.4161 psi/100 ft, -1.40% on the printed 0.422 (tolerance: the 3-decimal print, 0.12%). Two causes, both outside the Darcy-Colebrook march: (1) the PR package's methane density at the inlet is 39.103 kg/m3, +2.2% on the GERG-2008/CoolProp reference 38.264 kg/m3 (the book's Z = 0.905 gives 38.17 kg/m3), and dP scales as 1/rho; rescaled to the reference density the unit's drop would be 2931.8 Pa, +0.76%. (2) The residual is the friction basis: GPSA's C2 size factor (Fig. 17-9) bakes in a chart friction factor for clean steel, while R1 computes Colebrook at Re 8.78e6 with eps 4.57e-5 m (f = 0.01357). The reference-density packages (gerg2008, coolprop_heos) cannot run this case: their PH flash raises SaturationError for pure methane above its critical pressure (ngdesign.thermo.helmholtz._flash_H_or_S calls _tsat unconditionally) - a thermo bug reported to the orchestrator, outside this unit's scope. Level stays provisional.

## References

- docs/unit-catalogue-plan.md §2 U-B 8

> R1/R2 provisional (PR 291) — R1 is a single-phase Darcy-Colebrook march with elevation (Heun predictor-corrector, refined to 1e-6 of dP), R2 adds the Beggs-Brill two-phase profile (fluids, original 1973 holdup, no Payne correction) at a fixed N with the N/2 discretisation check, so a line can flash part-way. V1 gap — the spec's candidate printed sources were searched and are not accessible as open printed-result texts. Crane TP-410 (2013) ch. 4 and Darby & Chhabra (2017) ch. 6 worked examples exist openly only as the fluids library's own "solved problems" reproductions (excluded — library outputs, not the book's printed results), and the R2 candidates (Brill & Mukherjee, SPE Monograph 17, ch. 4; Shoham 2006, ch. 4) are paywalled monograph texts whose Beggs-Brill examples additionally need a black-oil/PVT basis the installed packages do not provide. The levels are pinned by the closed-form C1/C2 tests and the R0/R1/R2 identities instead.
