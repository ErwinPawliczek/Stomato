# Tank / surge drum (`tank`)

Family: **separation** · P&ID symbol: `TK`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | well-mixed outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.tank:Tank` | adiabatic PH mix at P = min inlet P (or a given P — refused when it exceeds the lowest inlet pressure — the tank does not raise pressure); info residence_time_s = volume_m3 / liquid volumetric flow (from the outlet liquid phases' density). Closed-form R0 — a pure mixer with spec quantities only, no correlation constants |

### R0 parameters

```yaml
properties:
  P:
    description: outlet pressure, Pa abs; default min inlet P
    type: number
  volume_m3:
    description: liquid holdup, m3; drives the residence-time report
    minimum: 0
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 5

> R0 mixer implemented; volume_m3 is an optional holdup report, not sizing.
