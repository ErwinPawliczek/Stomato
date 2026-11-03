# Divided-wall / Petlyuk column (`divided_wall`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed |
| outlet | `distillate` | yes | light product |
| outlet | `side_product` | yes | middle product |
| outlet | `bottoms` | yes | heavy product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | planned | — | two coupled MESH sections; P1-13 (the two-tear column core) and S0-1c steps 3-4 (side strippers solved simultaneously on the stage graph, units/column/strippers.py) are in, but the stage graph only appends side-stripper sections fed by a liquid draw and returning their top vapour; a dividing wall needs two parallel sections that split both the liquid and the vapour traffic (a vapour split is a new unknown with its own pressure-balance equation) and rejoin above and below the wall. Not attempted on this tree |

## References

- docs/unit-catalogue-plan.md §2 U-E 10

> roadmap.
