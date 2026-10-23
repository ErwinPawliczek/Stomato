# Expander / turbine (`expander`)

Family: **flow** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | gas feed |
| outlet | `gas_out` | yes | expanded gas (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.expander:Expander` | isentropic expansion with power recovery |
| R1 | planned | — | performance map |

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

## References

- docs/unit-catalogue-plan.md §2 U-B 4

> the hydraulic turbine / pressure-recovery line (plan U-B 12) is covered by this row — isentropic expansion recovering shaft power — not a separate row.
