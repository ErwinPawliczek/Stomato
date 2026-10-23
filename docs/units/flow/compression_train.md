# Compression train (`compression_train`)

Family: **flow** · P&ID symbol: `CT`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | gas feed to the first section |
| outlet | `gas_out` | yes | discharge of the last section after intercooling |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.compression_train:CompressionTrain` | multi-section compression with intercooling to a fixed interstage temperature |

### R0 parameters

```yaml
properties:
  P_discharge:
    description: final discharge pressure, Pa
    type: number
  T_interstage_out:
    description: interstage outlet temperature after cooling, K
    type: number
  eta_isentropic:
    description: per-section isentropic efficiency, default 0.75
    type: number
required:
- P_discharge
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 2 (today: train ✅)

> its own flow row per the plan-to-registry mapping — the plan's compressor R2 (multi-section with intercooling) lives here, not on the compressor row.
