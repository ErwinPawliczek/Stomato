# Stream calculator (set) (`stream_calculator`)

Family: **logical** · P&ID symbol: `SMC`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | reference stream |
| outlet | `outlet` | yes | copy/scale/override of the inlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | copy, scale or override stream variables (T, P, flow, composition) |

## References

- docs/unit-catalogue-plan.md §2 U-A 4

> P2-01 design specs exist at the solver level; the unit form is missing.
