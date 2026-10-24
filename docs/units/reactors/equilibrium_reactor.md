# Equilibrium reactor (Keq) (`equilibrium_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | equilibrium effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.equilibrium_reactor:EquilibriumReactor` | extents solve ln Q = ln K per reaction; ideal-gas quotient on the JANAF standard state |

### R0 parameters

```yaml
properties:
  approach_dT:
    description: K evaluated at T + approach_dT; 0 = full equilibrium
    type: number
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} (default isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-WGS-EQ` | R0 | `info.extent_wgsr` | 0.499071 | 0.499071 | abs 1e-05 | pass |
| `V1-WGS-EQ` | R0 | `outlet.outlet.composition.CO` | 0.250465 | 0.250465 | abs 1e-05 | pass |
| `V1-WGS-EQ` | R0 | `outlet.outlet.composition.CO2` | 0.249535 | 0.249535 | abs 1e-05 | pass |

- `V1-WGS-EQ`: Closed form from the JANAF databank WGS ln K(1100 K) = -0.007436 (U-F V2; cf. the CMU/Kitchin NIST-Webbook worked example at 1000 K)

## References

- docs/unit-catalogue-plan.md §2 U-F 3

> R0 implemented (U-F); cross-checks the Gibbs reactor to 1e-6 (U-F V2). The WGSR/Moe discrepancy is tracked by U-R (issue
