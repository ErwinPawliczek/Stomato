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
| R2 | planned | — | two coupled MESH sections; blocked on the column core, the plain two-tear side-draw column does not converge on nC4/nC5/nC6 at 3 bar (11 stages, M=1.4e-2, NS stalls; spec P1-13) and a section tear loop is the design S0-1c rejected. Needs the graph solver of S0-1c (unmerged branch s0-1c/2-graph-ns) extended to two parallel sections |

## References

- docs/unit-catalogue-plan.md §2 U-E 10

> roadmap.
