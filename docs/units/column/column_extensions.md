# Column extensions (draws, pumparounds, multiple feeds) (`column_extensions`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | main feed |
| outlet | `distillate` | yes | overhead product |
| outlet | `bottoms` | yes | bottoms product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | planned | — | side draws (exist), pumparounds (missing), multiple feeds, inter-stage heaters |

## References

- docs/unit-catalogue-plan.md §2 U-E 6

> the MESH extensions the S0 crude column builds on (plan §2b, after P1-11).
