# Assay feeder (`assay_feeder`)

Family: **refining** · P&ID symbol: `ASSAY`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `assay_in` | yes | crude assay data (A-01 data layer) |
| outlet | `cuts_out` | yes | pseudo-component stream at T, P, flow |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.assay_feeder:AssayFeeder` | assay (A-01) → pseudo-component stream at T, P, flow (spec U-H1, the inlet must match the declared slate exactly) |

### R0 parameters

```yaml
properties:
  P:
    description: outlet pressure (Pa abs)
    type: number
  T:
    description: outlet temperature (K)
    type: number
  assay_id:
    description: id of the stored A-01 assay whose slate is the feed
    type: string
required:
- assay_id
- T
- P
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2101` | R0 | `info.api_gravity` | 36 | 35.9358 | rel 0.01 | pass |
| `V2101` | R0 | `info.light_ends_vol_pct` | 5.11 | 5.11 | rel 0.005 | pass |

- `V2101`: Bagajewicz & Ji 2001, Ind. Eng. Chem. Res. 40, 617-626: Table 1 light-crude feed density 845 kg/m3 = 36.0 deg API; Table 2 light ends total 5.11 vol% (transcribed in data/assays/bagajewicz_ji_2001_light.yaml)

## References

- docs/unit-catalogue-plan.md §2 U-H 1

> roadmap; pairs with the A-01 assay work and the flowsheet-owned pseudo-components (P1-14); assay cutting is data-layer work.
