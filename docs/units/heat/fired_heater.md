# Fired heater (`fired_heater`)

Family: **heat** · P&ID symbol: `FH`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed (coil inlet) |
| outlet | `outlet` | yes | coil outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | duty, efficiency, fuel from LHV |
| R1 | planned | — | radiant/convective split (Lobo-Evans) |

## References

- docs/unit-catalogue-plan.md §2 U-C 7

> roadmap; S0 crude preheat train (plan §2b).
