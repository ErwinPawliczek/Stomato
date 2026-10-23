# Reactive stages (equilibrium / kinetic) (`reactive_stages`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed |
| outlet | `distillate` | yes | overhead |
| outlet | `bottoms` | yes | bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | planned | — | MESH + reaction set on the stage holdup (the reaction-set contract is U-R's) |

## References

- docs/unit-catalogue-plan.md §2 U-E 8

> amine chemistry lives in the property package, not the stage (plan note).
