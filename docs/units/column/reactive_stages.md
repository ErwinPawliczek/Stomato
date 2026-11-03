# Reactive stages (equilibrium / kinetic) (`reactive_stages`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed |
| outlet | `distillate` | yes | overhead |
| outlet | `bottoms` | yes | bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column_shortcut.reactive_stages:ReactiveStages` | MESH with kinetic source terms on the stage liquid holdup; equilibrium is the large-holdup limit, there is no chemical-equilibrium stage model; heat of reaction on the formation-enthalpy basis |

### R2 parameters

```yaml
additionalProperties: false
properties:
  condenser:
    description: total | partial | none
    type: string
  feed_stage:
    description: main feed stage
    type: integer
  n_stages:
    description: equilibrium stages, 1..N top to bottom
    type: integer
  pressure_profile:
    description: top pressure or per-stage profile, Pa
    type: number
  reaction_set:
    description: ReactionSet document; kinetics on the mole_fraction basis, reversible
      reactions by an explicit reverse rate
    type: object
  reactive_holdup_m3:
    description: '{stage: liquid holdup, m3}; never on a condenser or kettle stage'
    type: object
  reboiler:
    description: kettle | none
    type: string
  specs:
    description: one spec per tear, as the column row
    type: object
required:
- n_stages
- condenser
- reboiler
- feed_stage
- specs
- reaction_set
- reactive_holdup_m3
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 8
- Taylor & Krishna, Chem. Eng. Sci. 55 (2000) 5183
- Fogler, Elements of Chemical Reaction Engineering, Example 11-3 (example kinetics)

> Amine chemistry lives in the property package, not the stage (plan note). V1 gap — provisional without a case; checked by hand-evaluated stage rates, the zero-holdup reduction to the plain column, and the large-holdup limit on the book's K_C(T) (tests/units/column_shortcut/test_reactive_stages.py). A cold reactive mesh walks the holdup up from the plain column. Measured limits: the two-tear path does not converge on the narrow nC4/iC4 split with or without reaction (1 MPa, 12 stages), and the ethylene oxide hydration benchmark does not converge on PR on either path, also with or without reaction; the example therefore uses a one-tear kettle column with boilup_rate. A strongly displaced feed stalls the ladder (x_iC4 = 0.1, 1 m3 per stage at 50 mol/s boilup stops at 0.42 of the holdup).
