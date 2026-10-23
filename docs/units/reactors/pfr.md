# Plug-flow reactor (`pfr`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R1 planned, R2 planned, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | reactor effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | planned | — | kinetics, adiabatic/isothermal |
| R2 | planned | — | integrated along length with heat transfer and pressure drop (Ergun) |
| R3 | planned | — | catalyst deactivation, pellet effectiveness |

## References

- docs/unit-catalogue-plan.md §2 U-F 6

> roadmap; discretised units share one integrator (plan §2 note).
