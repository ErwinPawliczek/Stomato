# MDEA absorber (`mdea_absorber`)

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
| R0 | provisional | `ngdesign.units.mdea_absorber:MdeaAbsorber` | single-stage shortcut with Kent-Eisenberg equilibrium |
| R2 | planned | — | staged on the reactive package — blocked on P1-11 |

### R0 parameters

```yaml
properties:
  amine:
    description: solvent amine (a key of mdea_equilibrium.AMINES); the row default
      is MDEA
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

> amine chemistry lives in the property package, not the stage (plan note).
