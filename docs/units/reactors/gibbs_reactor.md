# Gibbs reactor (`gibbs_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | Gibbs-minimum effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.gibbs_reactor:GibbsReactor` | Gibbs minimisation at the stationarity conditions (element-potential method) |

### R0 parameters

```yaml
properties:
  inerts:
    description: fixed-amount spectators excluded from the minimisation
    type: array
  species:
    description: components allowed to react (element-potential Gibbs minimum)
    type: array
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} (default isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.CO` | 0.250465 | 0.250465 | abs 1e-05 | pass |
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.CO2` | 0.249535 | 0.249535 | abs 1e-05 | pass |
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.H2` | 0.249535 | 0.249535 | abs 1e-05 | pass |

- `V1-WGS-GIBBS`: Closed form from the JANAF databank WGS ln K(1100 K) = -0.007436 (U-F V2; cf. the CMU/Kitchin NIST-Webbook worked example at 1000 K)

## References

- docs/unit-catalogue-plan.md §2 U-F 4

> R0 implemented (U-F). Every feed component must be listed in species or inerts; restricted equilibria stay an R1+ concern.
