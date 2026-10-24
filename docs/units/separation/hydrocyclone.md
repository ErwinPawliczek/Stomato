# Hydrocyclone / cyclone (`hydrocyclone`)

Family: **separation** · P&ID symbol: `CYC`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | slurry/gas feed |
| outlet | `overflow` | yes | fine stream |
| outlet | `underflow` | yes | coarse stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.hydrocyclone:Hydrocyclone` | per-component split spec — the underflow is the spec, not a correlation constant; the overflow leaves at P_in - dP, the underflow at P_in. Evidence gap — Perry Sect. 18 cut-size sizing is R1, so no worked example validates a cut size at R0 (V0 self-consistency only). |
| R1 | planned | — | Lapple / Barth cut size |

### R0 parameters

```yaml
properties:
  dP:
    description: pressure drop, Pa; applied to the overflow outlet
    minimum: 0
    type: number
  underflow_fractions:
    description: component id to the fraction of its molar flow sent to the underflow;
      unnamed components go entirely to the overflow
    type: object
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 6

> R0 split spec implemented; deoiling example with 95 % water to the underflow.
