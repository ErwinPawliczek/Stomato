# TEG contactor (`teg_contactor`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | wet gas |
| inlet | `lean_teg_in` | yes | lean glycol (TEG) |
| outlet | `gas_out` | yes | dehydrated gas |
| outlet | `rich_teg_out` | yes | rich glycol |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.teg_contactor:TEGContactor` | activity-based water spec (GPSA/Parrish water-activity model) |
| R2 | provisional | `ngdesign.units.treating.teg_contactor_r2:TEGContactorR2` | stage-wise isothermal water absorption on the Parrish-Won-Baltatu activity line (rating at N stages) |

### R0 parameters

```yaml
properties:
  water_out_lb_per_mmscf:
    description: outlet water content spec
    lb/MMscf: null
    type: number
type: object
```

### R2 parameters

```yaml
additionalProperties: false
properties:
  n_stages:
    description: equilibrium stages (isothermal at the gas inlet T and P)
    minimum: 1
    type: integer
required:
- n_stages
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-G 3

> molecular-sieve dehydration (plan U-G 6) maps to separation's adsorption_bed row. R2 V1 gap — the GPSA Eng. Data Book Sect. 20 glycol-contactor example works on McCabe-Thiele/Kremser charts; no accessible page shows the printed inputs and a printed outlet water together, so no V1 case (searched GPSA Sect. 20 worked examples and open TEG-dehydration literature); chart reads are never presented as printed numbers, so the level ships provisional.
