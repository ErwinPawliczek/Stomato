# DEA regenerator (`dea_regenerator`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `rich_amine_in` | yes | rich amine |
| outlet | `lean_amine_out` | yes | lean amine bottoms |
| outlet | `acid_gas_out` | yes | acid gas overhead |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.mdea_regenerator:DeaRegenerator` | shortcut stripping to lean-loading specifications |
| R2 | provisional | `ngdesign.units.amine_regenerator_r2:DeaRegeneratorR2` | reboiled MESH stripper on the reactive amine package (amine_ke when the flowsheet package is not reactive), no overhead condenser - acid_gas_out is the wet top vapour. Measured (6 stages, 1.9 bar, 370 K feed) components close to 1e-10 at boilup 15/20/30 mol/s in 4-7 s, stage audit below 1e-9 / 1e-6 (the former single-phase re-flash of the top stage was a false liquid verdict in the package flash, fixed); the example runs at 30 mol/s |

### R0 parameters

```yaml
properties:
  amine:
    description: solvent amine; the row default is DEA
    type: string
  lean_co2_loading:
    description: lean solvent CO2 loading target
    mol CO2 / mol amine: null
    type: number
  lean_h2s_loading:
    description: lean solvent H2S loading target
    mol H2S / mol amine: null
    type: number
  reboiler_T:
    K: null
    description: reboiler temperature
    type: number
  regenerator_P:
    Pa: null
    description: regenerator pressure
    type: number
type: object
```

### R2 parameters

```yaml
additionalProperties: false
properties:
  boilup_rate:
    description: kettle vapour, mol/s
    type: number
  feed_T:
    description: rich solvent temperature after the lean/rich exchanger, K (default
      370)
    type: number
  n_stages:
    description: equilibrium stages, rich feed on 1, kettle on N (default 6)
    minimum: 2
    type: integer
  regenerator_P:
    description: column pressure, Pa abs (default 1.9e5)
    type: number
required:
- boilup_rate
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-G 2

> thin subclass of the MDEA regenerator.
