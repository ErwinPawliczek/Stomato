# MEA regenerator (`mea_regenerator`)

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
| R0 | provisional | `ngdesign.units.mdea_regenerator:MeaRegenerator` | shortcut stripping to lean-loading specifications |
| R2 | provisional | `ngdesign.units.amine_regenerator_r2:MeaRegeneratorR2` | reboiled MESH stripper on the reactive amine package (amine_ke when the flowsheet package is not reactive), no overhead condenser - acid_gas_out is the wet top vapour. Measured (6 stages, 1.9 bar, 370 K feed) components close to 3e-10 at boilup 35-60 mol/s in 6-14 s (cold), stage audit below 1e-9 / 1e-6; below 35 mol/s the cold heat-of-reaction ladder stalls and the column's boilup continuation (cold 2x/4x anchor, warm walk down) converges 30/25/20/15/10 mol/s in 32/35/45/74/87 s, components to 1e-13. The example stays at 40 mol/s - lean CO2 meets the 0.1 x rich bound (0.040) only from ~36 mol/s (0.0400 at 36, 0.057 at 30, 0.104 at 20) |

### R0 parameters

```yaml
properties:
  amine:
    description: solvent amine; the row default is MEA
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
