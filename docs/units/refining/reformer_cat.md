# Catalytic reformer (`reformer_cat`)

Family: **refining** · P&ID symbol: `RF`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `naphtha_in` | yes | naphtha feed |
| outlet | `reformate_out` | yes | reformate |
| outlet | `h2_out` | yes | hydrogen by-product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | lumped yield table (C5+ yield vs severity) |
| R1 | planned | — | Smith (1959) lumped kinetics |

## References

- docs/unit-catalogue-plan.md §2 U-H 8

> roadmap.
