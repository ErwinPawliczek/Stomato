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

## References

- docs/unit-catalogue-plan.md §2 U-B 8

> R1/R2 provisional (PR 291) — R1 is a single-phase Darcy-Colebrook march with elevation (Heun predictor-corrector, refined to 1e-6 of dP), R2 adds the Beggs-Brill two-phase profile (fluids, original 1973 holdup, no Payne correction) at a fixed N with the N/2 discretisation check, so a line can flash part-way. V1 gap — the spec's candidate printed sources were searched and are not accessible as open printed-result texts. Crane TP-410 (2013) ch. 4 and Darby & Chhabra (2017) ch. 6 worked examples exist openly only as the fluids library's own "solved problems" reproductions (excluded — library outputs, not the book's printed results), and the R2 candidates (Brill & Mukherjee, SPE Monograph 17, ch. 4; Shoham 2006, ch. 4) are paywalled monograph texts whose Beggs-Brill examples additionally need a black-oil/PVT basis the installed packages do not provide. The levels are pinned by the closed-form C1/C2 tests and the R0/R1/R2 identities instead.
