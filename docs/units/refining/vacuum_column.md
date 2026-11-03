# Vacuum distillation column (`vacuum_column`)

Family: **refining** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | reduced crude feed |
| outlet | `overhead` | yes | overhead (wash oil / vacuum gas oil) |
| outlet | `vgo_out` | yes | vacuum gas oil draw |
| outlet | `bottoms` | yes | vacuum residuum |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.vacuum_column:VacuumColumn` | cut-point fractionation at flash-zone P (spec U-H1 sharp cut on the reduced-crude feed; single VGO draw, the row's three ports) |
| R2 | provisional | `ngdesign.units.refining.vacuum_column_r2:VacuumColumnR2` | zero-tear MESH, no condenser and no reboiler - a top pumparound (fixed return T) condenses the gas oil, VGO a liquid draw on the pumparound stage; relaxation cold start (initialization relaxation, the standard start stalls at M ~ 1.0 on the 19-pseudo example feed). No separate wash-oil zone; one pumparound |

### R0 parameters

```yaml
properties:
  cut_points_K:
    description: two ascending TBP cut boundaries (K) for the three products
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

### R2 parameters

```yaml
additionalProperties: false
properties:
  n_stages:
    description: equilibrium stages, feed on the bottom stage N
    minimum: 3
    type: integer
  pressure_profile:
    description: stage pressures, Pa abs (scalar or per-stage list); default feed_in.P
  pumparound_flow_mol_s:
    description: top pumparound flow, drawn at vgo_stage, returned to stage 1
    exclusiveMinimum: 0
    type: number
  pumparound_return_T_K:
    description: pumparound return temperature, K
    exclusiveMinimum: 0
    type: number
  vgo_rate_mol_s:
    description: VGO liquid draw, mol/s
    exclusiveMinimum: 0
    type: number
  vgo_stage:
    description: stage of the VGO draw and the pumparound draw (default 2)
    minimum: 2
    type: integer
required:
- n_stages
- vgo_rate_mol_s
- pumparound_flow_mol_s
- pumparound_return_T_K
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2104` | R0 | `info.overhead_vol_pct` | 34.9476 | 34.9476 | rel 0.001 | pass |
| `V2104` | R0 | `info.vgo_out_vol_pct` | 39.8267 | 39.8267 | rel 0.001 | pass |
| `V2104` | R0 | `info.bottoms_vol_pct` | 25.2257 | 25.2257 | rel 0.001 | pass |

- `V2104`: Documented closed form: the example basis cuts the A-01 assay's pseudos above the AGO end point at 40 mmHg (Gary et al., Petroleum Refining, p. 77 vacuum conditions, as cited on the adapter example); shares recomputed independently from the slate mole fractions, MW and sg at cut points 755 K / 950 K

## References

- docs/unit-catalogue-plan.md §2 U-H 5

> roadmap.
