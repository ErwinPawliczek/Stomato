# Adjust (`adjust`)

Family: **logical** · P&ID symbol: `ADJ`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | stream carrying the target |
| outlet | `outlet` | yes | adjusted stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | manipulate a unit parameter to hit a stream target (wraps the solver design specs) |

## References

- docs/unit-catalogue-plan.md §2 U-A 5

> exists at solver level only today (plan marks the line 🟡).
