# Reciprocating compressor (`reciprocating_compressor`)

Family: **flow** · P&ID symbol: `RC`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | compressed gas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.reciprocating_compressor:ReciprocatingCompressor` | clearance-volume model, stages |
| R1 | provisional | `ngdesign.units.flow.reciprocating_compressor_r1:ReciprocatingCompressorR1` | per-stage cylinder capacity vs clearance (GPSA VE with Zs/Zd), clearance pocket, gas rod load |

### R1 parameters

```yaml
properties:
  P_crankcase_Pa:
    description: crankcase pressure, Pa, default 101325
    type: number
  P_out:
    description: outlet pressure, Pa
    type: number
  T_intercool:
    description: intercooler outlet temperature, K (optional)
    type: number
  capacity_control:
    description: default none
    enum:
    - none
    - clearance_pocket
    type: string
  cylinders:
    description: one entry per stage
    items:
      properties:
        action:
          description: default double
          enum:
          - double
          - single_head_end
          type: string
        bore_m:
          description: bore, m
          type: number
        clearance:
          description: clearance fraction, default 0.10
          type: number
        n_cylinders:
          description: parallel cylinders, default 1
          type: integer
        rod_diameter_m:
          description: rod diameter, m
          type: number
        stroke_m:
          description: stroke, m
          type: number
      required:
      - bore_m
      - stroke_m
      - rod_diameter_m
      type: object
    type: array
  eta_isentropic:
    description: stage isentropic efficiency, default 0.75
    type: number
  loss_allowance:
    description: valve-loss allowance L in E_v, default 0
    type: number
  n_stages:
    description: stages, default 1
    type: integer
  rod_load_limit_N:
    properties:
      compression:
        description: allowable gas rod load in compression, N
        type: number
      tension:
        description: allowable gas rod load in tension, N
        type: number
    type: object
  speed_rpm:
    description: crank speed, rpm
    type: number
  z_ratio_correction:
    description: Zs/Zd in volumetric efficiency, default true
    type: boolean
required:
- P_out
- cylinders
- speed_rpm
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 3

> R0 isentropic stages with intercooling and a clearance-volume volumetric-efficiency report. R1 adds per-stage cylinder capacity vs clearance (GPSA 13th ed. §13 VE with Zs/Zd), the closed-form clearance pocket and API 618 §6.6 gas rod loads. V1 gap: GPSA 13th ed. §13 worked examples, Bloch & Hoefner (1996) ch. 2–3, Ludwig Applied Process Design vol. 3 4th ed. ch. 15 and Perry's 9th ed. §10 are citation only. Searched 2026-10-25: the only accessible Section 13 reproduction (GPA Midstream public "Data Book Calculations", 14th ed. rev. 0 2017, Examples 13-1..13-5) prints BHP, discharge temperature, bottle volumes and chart-read power — no VE or rod-load case with printed geometry — so no V1 case is filed (U-R2: never invent a number).
