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
| R2 | planned | — | two coupled MESH sections; P1-13 (the two-tear column core) and the S0-1c step 2 graph Newton (units/column/graph_ns.py) are in, but the stage graph only appends side-stripper sections fed by a liquid draw and returning their top vapour; a dividing wall needs two parallel sections that split both the liquid and the vapour traffic and rejoin above and below the wall, which neither the graph builder nor the inside-out sweep handles. Not attempted on this tree |

## References

- docs/unit-catalogue-plan.md §2 U-E 10

> roadmap.
