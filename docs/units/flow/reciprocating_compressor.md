# Reciprocating compressor (`reciprocating_compressor`)

Family: **flow** · P&ID symbol: `RC`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | compressed gas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.reciprocating_compressor:ReciprocatingCompressor` | clearance-volume model, stages |
| R1 | provisional | `ngdesign.units.flow.reciprocating_compressor_r1:ReciprocatingCompressorR1` | per-stage cylinder capacity vs clearance (GPSA VE with Zs/Zd), clearance pocket, gas rod load |

## References

- docs/unit-catalogue-plan.md §2 U-B 3

> R0 isentropic stages with intercooling and a clearance-volume volumetric-efficiency report; rod load and capacity-vs-clearance remain roadmap.
