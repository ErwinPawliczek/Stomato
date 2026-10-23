# Atmospheric crude column (`crude_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `crude_in` | yes | heated crude feed |
| outlet | `overhead` | yes | naphtha overhead |
| outlet | `kero_out` | yes | kerosene side draw |
| outlet | `diesel_out` | yes | diesel side draw |
| outlet | `ago_out` | yes | atmospheric gas oil side draw |
| outlet | `bottoms` | yes | reduced crude bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | cut-point fractionation (TBP cut points, gap/overlap spec) |
| R2 | planned | — | MESH with side strippers, pumparounds, stripping steam, overflash (U-E 6 extensions; needs column_extensions, P1-11) |

## References

- docs/unit-catalogue-plan.md §2 U-H 3

> roadmap; needs pseudo-component preflash (P1-14) and column extensions (plan §2b).
