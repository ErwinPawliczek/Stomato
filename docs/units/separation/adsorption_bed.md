# Adsorption bed (TSA/PSA) (`adsorption_bed`)

Family: **separation** · P&ID symbol: `X`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | gas to the bed |
| outlet | `product_out` | yes | treated product |
| outlet | `regen_out` | no | regeneration (tail-gas) outlet during the cycle |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.adsorption_bed:AdsorptionBed` | adsorbate split spec to regen_out; product and desorbate flashed at their own T (product_T / regen_T, default feed T) and their own P; info cycle_time_s = capacity * bed_mass / adsorbate mass rate. The default capacity 0.10 kg/kg is the ~10 wt% design water loading GPSA quotes for molecular sieves (Sect. 20, dehydration) |
| R1 | planned | — | Langmuir isotherm, LUB |

### R0 parameters

```yaml
properties:
  bed_mass_kg:
    description: bed mass, kg
    minimum: 0
    type: number
  capacity_kg_per_kg:
    description: adsorbate loading, kg per kg bed
    minimum: 0
    type: number
  product_P:
    description: product outlet pressure, Pa abs; default feed P
    type: number
  regen_P:
    description: desorbate outlet pressure, Pa abs; default feed P
    type: number
  removal_fraction:
    description: component id -> fraction of its molar flow taken to the desorbate
    type: object
required:
- removal_fraction
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 9

> molecular-sieve dehydration (plan U-G 6) maps onto this row with a cycle — no separate treating row.
