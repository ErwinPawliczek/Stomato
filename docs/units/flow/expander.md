# Expander / turbine (`expander`)

Family: **flow** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | gas feed |
| outlet | `gas_out` | yes | expanded gas (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.expander:Expander` | isentropic expansion with power recovery |
| R1 | provisional | `ngdesign.units.flow.expander_r1:ExpanderR1` | performance map (eta vs u/c0, PCHIP, no extrapolation) driving the R0 expansion |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta_isentropic:
    description: isentropic efficiency in (0, 1], default 0.8
    type: number
required:
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  flow_max_m3_s:
    description: flow-capacity upper limit, m3/s (optional)
    type: number
  flow_min_m3_s:
    description: flow-capacity lower limit, m3/s (optional)
    type: number
  map:
    properties:
      efficiency:
        description: isentropic efficiency in (0, 1] at each velocity_ratio
        items:
          type: number
        type: array
      velocity_ratio:
        description: strictly increasing u/c0 points
        items:
          type: number
        type: array
    required:
    - velocity_ratio
    - efficiency
    type: object
  rotor_diameter_m:
    description: rotor tip diameter, m
    type: number
  speed_rpm:
    description: shaft speed, rpm
    type: number
required:
- P_out
- rotor_diameter_m
- speed_rpm
- map
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 4

> the hydraulic turbine / pressure-recovery line (plan U-B 12) is covered by this row — isentropic expansion recovering shaft power — not a separate row.
