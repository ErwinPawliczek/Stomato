# Pump (`pump`)

Family: **flow** · P&ID symbol: `P`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | liquid feed |
| outlet | `outlet` | yes | pressurised liquid (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.pump:Pump` | ΔP/outlet P with efficiency; PS flash on the outlet |
| R1 | planned | — | curve (head/efficiency vs flow) and NPSHa check |

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

## References

- docs/unit-catalogue-plan.md §2 U-B 1

> shaft power currently inlined in the unit; the pump_power correlation plugin exists.
