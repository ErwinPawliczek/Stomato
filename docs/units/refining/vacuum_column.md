# Vacuum distillation column (`vacuum_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | reduced crude feed |
| outlet | `overhead` | yes | overhead (wash oil / vacuum gas oil) |
| outlet | `vgo_out` | yes | vacuum gas oil draw |
| outlet | `bottoms` | yes | vacuum residuum |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | cut-point fractionation at flash-zone P |
| R2 | planned | — | MESH with pumparounds, no condenser, wash zone |

## References

- docs/unit-catalogue-plan.md §2 U-H 5

> roadmap.
