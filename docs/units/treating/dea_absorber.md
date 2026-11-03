# DEA absorber (`dea_absorber`)

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
| R0 | provisional | `ngdesign.units.mdea_absorber:DeaAbsorber` | single-stage shortcut with Kent-Eisenberg equilibrium |
| R2 | planned | — | re-measured on the P1-13 tree (zero-tear column on amine_ke, example feeds) - 3, 5 and 8 stages converge (13, 20, 83 s) but close components only to 1.1e-4, 2.1e-11 and 1.4e-3 (the reactive 1e-3 stage gate), and 4 stages fails (M=1.03e-3); not reliable against the locked 1e-6 balance, so no adapter ships |

### R0 parameters

```yaml
properties:
  amine:
    description: solvent amine; the row default is DEA
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
