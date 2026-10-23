# 2-phase separator / KO drum (`scrubber`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 planned

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
| R1 | planned | — | Souders-Brown sizing, carry-over at a given diameter (the souders_brown correlation plugin exists) |

Sizer plugin: `scrubber`

## References

- docs/unit-catalogue-plan.md §2 U-D 1

> the registered id stays `scrubber` (historical); the row is the palette's 2-phase separator.
