# Air cooler (`air_cooler`)

Family: **heat** · P&ID symbol: `AC`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed |
| outlet | `outlet` | yes | cooled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat_exchange:HeatExchanger` | approach / duty spec |
| R1 | planned | — | rating — bundle geometry, fan power, ht air-side correlation |

Sizer plugin: `air_cooler`

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K
    type: number
  dP:
    description: pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 3

> roadmap R1 lands with the S1 natural-gas slice (plan §2b).
