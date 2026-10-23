# Naphtha hydrotreater (`naphtha_ht`)

Family: **refining** · P&ID symbol: `HT`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `naphtha_in` | yes | naphtha feed |
| inlet | `h2_in` | yes | hydrogen feed |
| outlet | `treated_out` | yes | hydrotreated naphtha |
| outlet | `gas_out` | yes | H2S / offgas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | yield shift + H2 consumption + S/N removal spec |
| R1 | planned | — | lumped HDS/HDN kinetics in a PFR |

## References

- docs/unit-catalogue-plan.md §2 U-H 7

> roadmap.
