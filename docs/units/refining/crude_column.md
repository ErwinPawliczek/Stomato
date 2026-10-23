# Atmospheric crude column (`crude_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R2 planned, R3 planned

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
| R2 | planned | — | MESH with multiple side draws + steam stripping (needs column_extensions, P1-11) |
| R3 | planned | — | rate-based with film hydraulics |

## References

- docs/unit-catalogue-plan.md §2 U-H 1

> roadmap; needs pseudo-component preflash (P1-14) and column extensions (plan §2b).
