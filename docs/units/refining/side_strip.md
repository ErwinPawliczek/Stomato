# Side stripper (`side_strip`)

Family: **refining** · P&ID symbol: `SS`

Rigour ladder: R0 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `draw_in` | yes | side draw from the main column |
| inlet | `steam_in` | yes | stripping steam |
| outlet | `overhead_out` | yes | stripped product + steam back to the column |
| outlet | `bottoms_out` | yes | stripped liquid product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | steam-stripped draw, Kremser on pseudos |
| R2 | planned | — | MESH stage section coupled to the main column |

## References

- docs/unit-catalogue-plan.md §2 U-H 4

> roadmap.
