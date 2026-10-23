# Hydrocracker (`hcu`)

Family: **refining** · P&ID symbol: `HC`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `vgo_in` | yes | VGO feed |
| inlet | `hydrogen_in` | yes | hydrogen feed |
| outlet | `naphtha_out` | yes | hydrocracked naphtha |
| outlet | `diesel_out` | yes | diesel |
| outlet | `unconverted_out` | yes | unconverted oil recycle |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | yield table vs conversion |
| R1 | planned | — | lumped (continuous-lumping) kinetics |

## References

- docs/unit-catalogue-plan.md §2 U-H 10

> roadmap.
