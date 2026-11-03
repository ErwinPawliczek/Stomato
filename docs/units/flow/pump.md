# Pump (`pump`)

Family: **flow** · P&ID symbol: `P`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | liquid feed |
| outlet | `outlet` | yes | pressurised liquid (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.pump:Pump` | ΔP/outlet P with efficiency; PS flash on the outlet |
| R1 | provisional | `ngdesign.units.flow.pump_r1:PumpR1` | curve (head/efficiency vs flow, PCHIP, affinity laws) and NPSHa check; delegates the outlet to R0 |

Sizer plugin: `pump`

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta:
    description: pump efficiency in (0, 1], default 0.65
    type: number
required:
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  curve:
    properties:
      efficiency:
        description: efficiency at each flow point, (0, 1]
        items:
          type: number
        type: array
      flow_m3_s:
        description: curve flow points, m3/s, strictly increasing
        items:
          type: number
        type: array
      head_m:
        description: head at each flow point, m
        items:
          type: number
        type: array
      npsh_required_m:
        description: NPSHr at each flow point, m
        items:
          type: number
        type: array
    required:
    - flow_m3_s
    - head_m
    type: object
  eta:
    description: constant efficiency when the curve has none, (0, 1]
    type: number
  friction_head_m:
    description: suction friction head, m, default 0
    type: number
  npsh_check:
    description: default refuse
    enum:
    - refuse
    - report
    type: string
  speed_ratio:
    description: N / N_curve for the affinity laws, default 1.0
    type: number
  static_head_m:
    description: suction static head, m, default 0
    type: number
required:
- curve
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 1

> shaft power currently inlined in the unit; the pump_power correlation plugin exists. R1 V1 gap - no open worked example printing a full curve, fluid state and resulting P_out or NPSHa was found or searched for in this pass; provisional on the spec hand calculations and the exact R0 delegation.
