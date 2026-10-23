# JT valve (`jt_valve`)

Family: **flow** · P&ID symbol: `V`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | isenthalpic (flash_ph) outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.jt_valve:JTValve` | isenthalpic flash to the outlet pressure |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
required:
- P_out
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 5

> the palette defines no higher level for the JT valve (plan §2 U-B 5).
