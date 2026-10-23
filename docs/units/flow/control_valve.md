# Control valve (`control_valve`)

Family: **flow** · P&ID symbol: `CV`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | throttled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | Cv / outlet P spec, isenthalpic (the cv_liquid correlation plugin exists) |
| R1 | planned | — | IEC 60534 sizing, choked flow, Cv curve |

## References

- docs/unit-catalogue-plan.md §2 U-B 6

> roadmap.
