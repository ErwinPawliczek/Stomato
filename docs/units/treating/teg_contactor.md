# TEG contactor (`teg_contactor`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

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
| R2 | planned | — | staged with the TEG activity package — S1 slice (plan §2b) |

### R0 parameters

```yaml
properties:
  water_out_lb_per_mmscf:
    description: outlet water content spec
    lb/MMscf: null
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-G 3

> molecular-sieve dehydration (plan U-G 6) maps to separation's adsorption_bed row.
