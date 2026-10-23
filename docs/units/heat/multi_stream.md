# Multi-stream exchanger (LNG cold box) (`multi_stream`)

Family: **heat** · P&ID symbol: `MS`

Rigour ladder: R0 planned, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | first process stream |
| outlet | `outlet` | yes | first process stream outlet (further streams via params) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | stream-by-stream duties, composite curves, pinch check |
| R1 | planned | — | layer-wise UA distribution |
| R2 | planned | — | zoned with phase change |

## References

- docs/unit-catalogue-plan.md §2 U-C 6

> roadmap.
