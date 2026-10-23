# Delayed coker / visbreaker (`coker`)

Family: **refining** · P&ID symbol: `CK`

Rigour ladder: R0 planned

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
| R0 | planned | — | yield table vs CCR / severity |

## References

- docs/unit-catalogue-plan.md §2 U-H 11

> roadmap; the refinery_leeps_distillation correlation plugin exists for LEEP cut yields.
