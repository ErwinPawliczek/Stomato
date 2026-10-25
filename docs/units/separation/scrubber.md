# 2-phase separator / KO drum (`scrubber`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | two-phase feed |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `liquid_out` | yes | liquid outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separator:Scrubber` | PT/PH/PVF flash with ΔP; gas and liquid leave at their flash states |
| R1 | provisional | `ngdesign.units.separation.scrubber_r1:ScrubberR1` | Souders-Brown sizing (York demister K) and droplet carry-over at a given diameter; reduces to R0 without diameter_m or at E = 0 |

Sizer plugin: `scrubber`

### R1 parameters

```yaml
properties:
  K_m_s:
    description: Souders-Brown K, m/s; default York demister fit at the drum pressure
    exclusiveMinimum: 0
    type: number
  dP:
    description: pressure drop, Pa; default 0 (R0)
    minimum: 0
    type: number
  diameter_m:
    description: vessel inside diameter, m; enables the carry-over calculation
    exclusiveMinimum: 0
    type: number
  droplet_d_rr_m:
    description: Rosin-Rammler characteristic droplet size, m
    exclusiveMinimum: 0
    type: number
  droplet_n_rr:
    description: Rosin-Rammler spread parameter
    exclusiveMinimum: 0
    type: number
  gas_viscosity_Pa_s:
    description: gas viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  inlet_entrained_fraction:
    description: fraction of the liquid entering the gravity section as droplets
    maximum: 1
    minimum: 0
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 1

> the registered id stays `scrubber` (historical); the row is the palette's 2-phase separator.
