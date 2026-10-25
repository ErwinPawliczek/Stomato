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
| `V1-FOGLER-CONV` | R0 | `outlet.outlet.T` | 351.7 | 349.543 | abs 0.5 | assessed miss |

- `V1-FOGLER-CONV`: Fogler, Elements of Chemical Reaction Engineering, 4th ed., Example 8-3 (adiabatic n-butane isomerization): T = 330 + 43.4 X on the book feed (90 % n-butane + 10 % i-pentane inert, liquid phase; Θ_I = 0.111 mol inert per mol n-butane)
  - assessed: The temperature comparison misses by 2.2 K: the book's constant-Cp correlation T = 330 + 43.4·X gives 351.7 K (ΔT = 21.7 K), while the model measures 349.543 K (ΔT = 19.54 K). The book's slope is ΔH°rx/ΘCp = 6900/159 = 43.4 K per unit conversion; the model's is the JANAF databank's ΔH°rx ≈ −9510 J/mol over the measured mixture Cp of the book feed (nC4 + iC5 inert, 266.6 J/mol·K at the inlet state, finite difference of the model's molar enthalpy), about 35.7 K, so the adiabatic rise is smaller. Data-source and Cp-treatment differences, documented rather than tuned away; no tolerance is widened to hide it. (Before issue #247 the formation-basis enthalpy counted sensible heat twice and this case measured 342.872 K.)

## References

- docs/unit-catalogue-plan.md §2 U-F 1

> R0 implemented (U-F). Components absent from the reaction set pass through.
