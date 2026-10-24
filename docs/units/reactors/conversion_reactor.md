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
| R0 | provisional | `ngdesign.units.reactors.conversion_reactor:ConversionReactor` | fractional conversion per reaction (simultaneous or sequential); outlet flashed at inlet P; info carries extents |

### R0 parameters

```yaml
properties:
  conversion:
    description: '{reaction_id: fraction of the reaction base component converted}'
    type: object
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  sequential:
    description: 'true: each conversion applies to the amounts left by the preceding
      reactions (declaration order); default false: all conversions on the inlet basis'
    type: boolean
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K} (default
      isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-FOGLER-CONV` | R0 | `outlet.outlet.composition.iC4` | 0.45 | 0.45 | abs 1e-06 | pass |
| `V1-FOGLER-CONV` | R0 | `outlet.outlet.T` | 351.7 | 342.872 | abs 0.5 | assessed miss |

- `V1-FOGLER-CONV`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Example 8-3 (adiabatic n-butane isomerization): T = 330 + 43.4 X on the book feed (90% n-butane + 10% i-pentane inert, 2 mol inert per mol n-butane)
  - assessed: The composition check is exact (X = 0.5 on the 4.5 mol/s nC4 feed gives 4.5 mol/s iC4 + 4.5 nC4 + 1.0 iC5 inert, total 10.0 mol/s; y_iC4 = 0.45). The temperature comparison misses: the book's constant-Cp correlation T = 330 + 43.4·X gives 351.7 K (ΔT = 21.7 K), while the model measures 342.872 K (ΔT = 12.87 K) on the JANAF databank's ΔH°rx ≈ −9510 J/mol and PR gas heat capacities. The book's slope combines ΔH°rx = −6900 J/mol with a much smaller assumed lumped Cp (ΘCp ≈ 159 J/mol·K); the mixture Cp of the actual book feed (nC4 + iC5 inert) measures 266.6 J/mol·K at the inlet state (finite difference of the model's molar enthalpy), and PR's larger Cp more than offsets the larger |ΔH°rx|, so the adiabatic rise is smaller. Data-source and Cp-treatment differences, documented rather than tuned away; no tolerance is widened to hide it.

## References

- docs/unit-catalogue-plan.md §2 U-F 1

> R0 implemented (U-F). Components absent from the reaction set pass through.
