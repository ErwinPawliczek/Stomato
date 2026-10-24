# Yield reactor (`yield_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | effluent at the specified product yields |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.yield_reactor:YieldReactor` | product mass yields; the shift enforces mass closure, no reaction set required |

### R0 parameters

```yaml
properties:
  feed_components:
    description: lumped feed components consumed by the reactor
    type: array
  products:
    description: outlet components, aligned with yields_mass
    type: array
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} (default isothermal)'
  yields_mass:
    description: "kg product per kg consumed feed, \u03A3 = 1"
    type: array
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-SMR-YIELD` | R0 | `outlet.outlet.molar_flow` | 69 | 69 | abs 1e-06 | pass |
| `V1-SMR-YIELD` | R0 | `outlet.outlet.composition.CH4` | 0.043478 | 0.0434783 | abs 1e-06 | pass |
| `V1-SMR-YIELD` | R0 | `outlet.outlet.composition.H2O` | 0.478261 | 0.478261 | abs 1e-06 | pass |
| `V1-SMR-YIELD` | R0 | `outlet.outlet.composition.CO` | 0.101449 | 0.101449 | abs 1e-06 | pass |
| `V1-SMR-YIELD` | R0 | `outlet.outlet.composition.H2` | 0.304348 | 0.304348 | abs 1e-06 | pass |
| `V1-SMR-YIELD` | R0 | `outlet.outlet.composition.N2` | 0.072464 | 0.0724638 | abs 1e-06 | pass |

- `V1-SMR-YIELD`: Closed form: the conversion reactor's SMR example basis (10 CH4 + 40 H2O + 5 N2 at X = 0.7) — outlet amounts CH4 3, H2O 33, CO 7, H2 21, N2 5, total 69

## References

- docs/unit-catalogue-plan.md §2 U-F 2

> R0 implemented (U-F). Undeclared components pass through unconverted.
