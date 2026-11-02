# Multiphase Gibbs reactor (`gibbs_multiphase`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `vapor_out` | yes | equilibrium gas |
| outlet | `condensed_out` | yes | pure condensed species that formed (zero flow when none does) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.gibbs_multiphase:GibbsMultiphase` | Gibbs minimum over a gas and pure condensed phases on the cited species models; which phases exist is an output |

### R0 parameters

```yaml
properties:
  inerts:
    description: fixed-amount gas spectators
    type: array
  species:
    description: 'candidates: a bare id is the gas, ''C(s)'' and ''H2O(l)'' are pure
      condensed phases'
    type: array
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K} (default
      isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-CRACK-GIBBS` | R0 | `outlet.vapor_out.composition.H2` | 0.984873 | 0.985375 | abs 0.001 | pass |
| `V1-CRACK-GIBBS` | R0 | `outlet.vapor_out.composition.CH4` | 0.015127 | 0.0146247 | abs 0.001 | pass |

- `V1-CRACK-GIBBS`: JANAF Thermochemical Tables (Chase 1998), printed log Kf of CH4 at 1200 K: -1.807 (janaf.nist.gov C-067, formation from graphite and H2) -> K = y_CH4/y_H2^2 at 1 bar, y_H2 = (-1 + sqrt(1 + 4K))/(2K) = 0.984873

## References

- Gordon, S. and McBride, B.J., NASA RP-1311, 1994

> added by spec C-02; the gas-only palette row is gibbs_reactor
