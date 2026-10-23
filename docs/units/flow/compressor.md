# Centrifugal compressor (`compressor`)

Family: **flow** · P&ID symbol: `C`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | compressed gas (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.compressor:Compressor` | isentropic/polytropic efficiency; PS flash on the outlet |
| R1 | planned | — | performance map (head/efficiency vs flow, surge/stonewall), Schultz polytropic |

Sizer plugin: `compressor`

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta_isentropic:
    description: isentropic efficiency in (0, 1], default 0.75
    type: number
required:
- P_out
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 2

> multi-section compression with intercooling is its own flow row (compression_train), not a level of this row.
