# Atmospheric crude column (`crude_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `crude_in` | yes | heated crude feed |
| inlet | `stripping_steam` | no | stripping steam; its water (H2O) reports to the overhead |
| outlet | `overhead` | yes | naphtha overhead |
| outlet | `kero_out` | yes | kerosene side draw |
| outlet | `diesel_out` | yes | diesel side draw |
| outlet | `ago_out` | yes | atmospheric gas oil side draw |
| outlet | `bottoms` | yes | reduced crude bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.crude_column:CrudeColumn` | cut-point fractionation (TBP cut points, gap/overlap spec) — spec U-H1 sharp cut, light ends and water to the overhead; optional stripping_steam inlet carries its water to the overhead at R0 (one net duty) |
| R2 | planned | — | MESH with side strippers, pumparounds, stripping steam, overflash (U-E 6 extensions; needs column_extensions, P1-11) |

### R0 parameters

```yaml
properties:
  cut_points_K:
    description: four ascending TBP cut boundaries (K) for the five products
    items:
      type: number
    type: array
  draws:
    description: per-port {T, P} draw conditions (default the feed state)
    type: object
  overlap_K:
    description: linear split band (K) at each cut boundary (default 0)
    type: number
required:
- cut_points_K
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2103` | R0 | `info.overhead_vol_pct` | 32.0661 | 32.0661 | rel 0.001 | pass |
| `V2103` | R0 | `info.kero_out_vol_pct` | 30.7684 | 30.7684 | rel 0.001 | pass |
| `V2103` | R0 | `info.diesel_out_vol_pct` | 24.2067 | 24.2067 | rel 0.001 | pass |
| `V2103` | R0 | `info.ago_out_vol_pct` | 3.6697 | 3.66972 | rel 0.001 | pass |
| `V2103` | R0 | `info.bottoms_vol_pct` | 9.2891 | 9.2891 | rel 0.001 | pass |

- `V2103`: Documented closed form on the published A-01 assay (Bagajewicz & Ji 2001 Table 1-2 data, transcribed in data/assays/bagajewicz_ji_2001_light.yaml): sharp-cut assignment by normal boiling point at the four cut points; each product share recomputed independently from the slate mole fractions, MW and sg. The paper's open copy prints no product yields (s0_reference.yaml gaps)

## References

- docs/unit-catalogue-plan.md §2 U-H 3

> roadmap; needs pseudo-component preflash (P1-14) and column extensions (plan §2b).
