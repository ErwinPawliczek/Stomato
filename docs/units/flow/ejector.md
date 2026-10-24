# Ejector (`ejector`)

Family: **flow** · P&ID symbol: `EJ`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `motive_in` | yes | motive stream |
| inlet | `suction_in` | yes | suction stream |
| outlet | `outlet` | yes | combined discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.ejector:Ejector` | entrainment ratio spec |
| R1 | planned | — | 1-D momentum (ESDU-style) |

## References

- docs/unit-catalogue-plan.md §2 U-B 10

> R0 momentum balance at a specified entrainment ratio. V1 gap (PR
