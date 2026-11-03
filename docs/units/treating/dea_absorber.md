# DEA absorber (`dea_absorber`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional

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
| R2 | provisional | `ngdesign.units.amine_absorber_r2:DeaAbsorberR2` | countercurrent MESH absorber on the reactive amine package (amine_ke when the flowsheet package is not reactive), adiabatic, at the gas pressure; stage K_i(T, x) and phase enthalpies (heat of absorption included) read at the stage compositions. Measured (example feeds) components close to 1e-12 relative or better at 3/4/5/8/12/20 stages in 2-23 s; example-case stage audit below 1e-9 / 1e-6, column closure under 1 W |

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

### R2 parameters

```yaml
additionalProperties: false
properties:
  n_stages:
    description: equilibrium stages, lean solvent on 1, gas on N (default 8)
    minimum: 2
    type: integer
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-G 1

> thin subclass of the MDEA absorber over the same equilibrium model.
