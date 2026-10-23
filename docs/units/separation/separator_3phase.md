# 3-phase separator (`separator_3phase`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | three-phase feed |
| outlet | `gas_out` | yes | vapour outlet |
| outlet | `hc_out` | yes | hydrocarbon liquid outlet |
| outlet | `water_out` | yes | water outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separator:Separator3Phase` | VLLE flash; gas, hydrocarbon and water leave at their phase states |

Sizer plugin: `separator_3phase`

## References

- docs/unit-catalogue-plan.md §2 U-D 2

> roadmap R1 lands with the S1 slice (plan §2b).
