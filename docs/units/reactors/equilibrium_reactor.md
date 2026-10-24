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
| R0 | provisional | `ngdesign.units.reactors.equilibrium_reactor:EquilibriumReactor` | extents solve ln Q = ln K(T_out − approach_K) per reaction; ideal-gas quotient on the JANAF standard state; info reports ln K at the temperature actually used; a solve that pushes a species negative or past depletion is refused, never clipped |

### R0 parameters

```yaml
properties:
  approach_K:
    description: "K evaluated at T_out \u2212 approach_K; 0 = full equilibrium. Sign\
      \ convention \u2014 equilibrium evaluated at the temperature that gives LESS\
      \ conversion than ideal (positive falls short for an endothermic reaction; negative\
      \ for an exothermic one, matching U-G's Claus T_out + approach on the hot side)"
    type: number
  reaction_set:
    description: inline ReactionSet, or a string id resolved against Flowsheet.reactions
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K} (default
      isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-WGS-EQ` | R0 | `info.extent_wgsr` | 0.498846 | 0.499071 | abs 0.001 | pass |
| `V1-WGS-EQ` | R0 | `outlet.outlet.composition.CO` | 0.250577 | 0.250465 | abs 0.001 | pass |
| `V1-WGS-EQ` | R0 | `outlet.outlet.composition.CO2` | 0.249423 | 0.249535 | abs 0.001 | pass |

- `V1-WGS-EQ`: JANAF Thermochemical Tables (Chase 1998), printed log Kf at 1100 K: CO2 18.805, CO 9.928, H2O 8.881 (janaf.nist.gov C-095/C-093/H-064) -> log K(WGS) = -0.004; X = sqrt(K)/(1+sqrt(K)) = 0.498846

## References

- docs/unit-catalogue-plan.md §2 U-F 3

> R0 implemented (U-F); cross-checks the Gibbs reactor to 1e-6 (U-F V2). The WGSR/Moe discrepancy is tracked by U-R (issue
