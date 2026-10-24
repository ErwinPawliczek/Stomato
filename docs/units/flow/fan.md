# Fan / blower (`fan`)

Family: **flow** · P&ID symbol: `FAN`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | raised-pressure gas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.fan:Fan` | ΔP + efficiency |
| R1 | planned | — | performance curve |

## References

- docs/unit-catalogue-plan.md §2 U-B 11

> R0 fixed dP rise with efficiency; performance curves remain roadmap.
