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
| R2 | planned | — | re-measured on the P1-13 tree - the zero-tear column on this row's example feed leaves the package domain at 5 stages (speciation pressure vanished for CO2 at 335.4 K, 1.4 s); no adapter ships until that closes |

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
