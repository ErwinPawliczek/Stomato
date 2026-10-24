# Relief valve (`relief_valve`)

Family: **flow** · P&ID symbol: `PSV`

Rigour ladder: R0 provisional, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | relieved stream at set pressure |
| outlet | `outlet` | yes | discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.relief_valve:ReliefValve` | set pressure, orifice from API 520 (the psv_api520_gas correlation plugin exists) |
| R1 | planned | — | two-phase sizing (HEM/omega) |
| R2 | planned | — | inlet/outlet loss checks |

## References

- docs/unit-catalogue-plan.md §2 U-B 7

> R0 gas PSV sizing per API 520 Part I with API 526 orifice selection. V1 gap (PR
