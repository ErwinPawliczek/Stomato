# Decanter (`decanter`)

Family: **separation** · P&ID symbol: `V`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | LLE feed |
| outlet | `light_out` | yes | light liquid phase |
| outlet | `heavy_out` | yes | heavy liquid phase |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.decanter:Decanter` | PT flash at (T_in, P_in - dP); the two liquid phases leave light/heavy by phase density; a single-liquid or vapour-returning flash is refused, naming T and P. Evidence gap — V0 self-consistency only — no cited worked example validates a decanter split at R0 |
| R1 | planned | — | settling (Stokes) |

### R0 parameters

```yaml
properties:
  dP:
    description: pressure drop, Pa; default 0
    minimum: 0
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 4

> R0 LLE split implemented; Stokes settling sizing is R1 (plan §2b).
