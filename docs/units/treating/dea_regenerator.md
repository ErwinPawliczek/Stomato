# DEA regenerator (`dea_regenerator`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

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
| R2 | planned | — | measured on the P1-13 tree (6-stage kettle stripper on amine_ke, 1.9 bar, rich feed at 370 K) - the column converges and closes components (1.8e-6 at boilup 20, 2.6e-10 at 30 mol/s), but the independent stage audit fails - the top stage's L+V contents re-flash single-phase on the package (equilibrium residual 1.0), so no adapter ships |

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

## References

- docs/unit-catalogue-plan.md §2 U-G 2

> thin subclass of the MDEA regenerator.
