# Pipe segment (`pipe_segment`)

Family: **flow** · P&ID symbol: `PIPE`

Rigour ladder: R0 planned, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | segment inlet |
| outlet | `outlet` | yes | segment outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | fixed ΔP spec |
| R1 | planned | — | single-phase Darcy (Colebrook) with elevation; the darcy_colebrook correlation plugin exists |
| R2 | planned | — | two-phase Beggs-Brill / fluids multiphase, profile along the length |

## References

- docs/unit-catalogue-plan.md §2 U-B 8

> roadmap.
