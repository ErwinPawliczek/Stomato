# Three-phase (VLLE) stages (`three_phase_stages`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed forming two liquids |
| outlet | `distillate` | yes | overhead |
| outlet | `bottoms` | yes | bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column_shortcut.three_phase_stages:ThreePhaseStages` | MESH on the overall (pooled) stage liquid with K = y/xbar from the stage VLLE flash; the split is reported per stage and a re-flash gate refuses stages off equilibrium; no decanter, both liquids flow down together |

### R2 parameters

```yaml
additionalProperties: false
properties:
  condenser:
    description: total | partial | none
    type: string
  feed_stage:
    description: feed stage
    type: integer
  n_stages:
    description: equilibrium stages, 1..N top to bottom
    type: integer
  pressure_profile:
    description: top pressure or per-stage profile, Pa
    type: number
  reboiler:
    description: kettle | none
    type: string
  specs:
    description: one spec per tear, as the column row
    type: object
required:
- n_stages
- condenser
- reboiler
- feed_stage
- specs
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 7
- Block & Hegner, AIChE J. 22 (1976) 582
- Cairns & Furzer, I&EC Res. 29 (1990) 1349

> V1 gap — provisional without a case; checked by isofugacity of the three reported phases, a stage audit on fresh three-phase flashes, and the single-liquid reduction (tests/units/column_shortcut/test_three_phase_stages.py). Measured limit: a two-tear wet nC6/nC7 column with a total condenser does not converge (M = 1 from the cold seed), so the example is a one-tear kettle column.
