# MEA absorber (`mea_absorber`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | sour gas |
| inlet | `lean_amine_in` | yes | lean amine |
| outlet | `gas_out` | yes | treated (sweet) gas |
| outlet | `rich_amine_out` | yes | rich amine |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.mdea_absorber:MeaAbsorber` | single-stage shortcut with Kent-Eisenberg equilibrium |
| R2 | planned | — | the domain exit is fixed at its root (the Kent-Eisenberg carbamate balance returned hco3 = 0 below its Brent tolerance at a trace CO2 loading of 1.9e-14 beside H2S 0.44; trace CO2 is now solved in ln hco3). Re-measured - the zero-tear 5-stage column on this row's example feed now converges (31 s) but closes components only to 4.7e-4 relative per component (the reactive 1e-3 stage gate), short of the locked 1e-6 balance, so no adapter ships |

### R0 parameters

```yaml
properties:
  amine:
    description: solvent amine; the row default is MEA
    type: string
  co2_out_molpct:
    description: treated-gas CO2 spec
    mol%: null
    type: number
  h2s_out_ppmv:
    description: treated-gas H2S spec
    ppmv: null
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-G 1

> thin subclass of the MDEA absorber over the same equilibrium model.
