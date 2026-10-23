# Heater (`heater`)

Family: **heat** · P&ID symbol: `E`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed |
| outlet | `outlet` | yes | heated outlet (PH flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat_exchange:HeatExchanger` | duty or outlet T with ΔP |

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

## References

- docs/unit-catalogue-plan.md §2 U-C 1

> heater and cooler are separate rows. The electric-heater line (plan U-C 9, R0 duty only) maps onto this row — no separate electric-heater row.
