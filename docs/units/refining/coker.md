# Coker (delayed) (`coker`)

Family: **refining** · P&ID symbol: `CK`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | residuum feed |
| outlet | `gas_out` | yes | coker gas |
| outlet | `naphtha_out` | yes | coker naphtha |
| outlet | `lgo_out` | yes | light gas oil |
| outlet | `hgo_out` | yes | heavy gas oil |
| outlet | `coke_out` | yes | petroleum coke |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | yield correlation spec (the refinery_leeps_distillation correlation plugin exists for LEEP cut yields) |
| R1 | planned | — | kinetic coking model |

## References

- docs/unit-catalogue-plan.md §2 U-H 3

> roadmap.
