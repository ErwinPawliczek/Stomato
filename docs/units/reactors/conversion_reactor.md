# Conversion reactor (`conversion_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | effluent at specified conversion |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.conversion_reactor:ConversionReactor` | fractional conversion per reaction; outlet flashed at inlet P; info carries extents |

### R0 parameters

```yaml
properties:
  conversion:
    description: '{reaction_id: fraction of the reaction base component converted}'
    type: object
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} (default isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-FOGLER-CONV` | R0 | `outlet.outlet.composition.iC4` | 0.5 | 0.5 | abs 1e-06 | pass |
| `V1-FOGLER-CONV` | R0 | `outlet.outlet.T` | 351.7 | 344.4 | abs 0.5 | assessed miss |

- `V1-FOGLER-CONV`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Example 8-3 (adiabatic n-butane isomerization): T = 330 + 43.4 X
  - assessed: The composition check is exact (X = 0.5 fixed by the conversion spec; outlet amounts 5.0/5.0 mol/s). The temperature comparison misses: the book's constant-Cp correlation T = 330 + 43.4·X gives 351.7 K (ΔT = 21.7 K), while the model measures 344.400 K (ΔT = 14.40 K) on the JANAF databank's ΔH°rx ≈ −9510 J/mol and PR gas heat capacities. The book's slope combines ΔH°rx = −6900 J/mol with a much smaller assumed Cp (≈ 159 J/mol·K); the larger |ΔH| is more than offset by PR's larger Cp (≈ 330 J/mol·K), so the adiabatic rise is smaller. Data-source and Cp-treatment differences, documented rather than tuned away; no tolerance is widened to hide it.

## References

- docs/unit-catalogue-plan.md §2 U-F 1

> R0 implemented (U-F). Components absent from the reaction set pass through.
