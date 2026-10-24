# Filter (`filter`)

Family: **separation** · P&ID symbol: `FLT`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | slurry feed |
| outlet | `filtrate` | yes | clear filtrate |
| outlet | `cake` | yes | solids cake |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.filter:Filter` | per-component split spec — the cake split is the spec, not a correlation constant; the filtrate leaves at P_in - dP, the cake at P_in. Evidence gap — cake-resistance physics is R1, so no worked example validates a cake at R0 (V0 self-consistency only). |
| R1 | planned | — | cake resistance |

### R0 parameters

```yaml
properties:
  cake_fractions:
    description: component id to the fraction of its molar flow sent to the cake;
      unnamed components pass entirely to the filtrate
    type: object
  dP:
    description: pressure drop, Pa; applied to the filtrate outlet (the cake leaves
      at the inlet pressure)
    minimum: 0
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 7

> roadmap.
