# Recycle block (`recycle_block`)

Family: **logical** · P&ID symbol: `RCY`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | torn stream guess |
| outlet | `outlet` | yes | accelerated tear stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | explicit tear with per-block acceleration options |

## References

- docs/unit-catalogue-plan.md §2 U-A 7

> tear handling is implicit in the solver today (P2-03).
