# Column extensions (draws, pumparounds, multiple feeds) (`column_extensions`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | main feed |
| inlet | `feed_2` | no | second feed (stage from feed_2_stage) |
| outlet | `distillate` | yes | overhead product |
| outlet | `bottoms` | yes | bottoms product |
| outlet | `side_draw` | no | side draw (zero-flow state when none is configured) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column_shortcut.column_extensions:ColumnExtensions` | the column row's MESH with a second feed port, one draw port, fixed pumparounds and fixed-duty inter-stage heaters/coolers in the same stage equations; free (spec-driven) draw and pumparound rates are not implemented |

### R2 parameters

```yaml
additionalProperties: false
properties:
  condenser:
    description: total | partial | none
    type: string
  feed_2_stage:
    description: second feed stage (required when feed_2 is connected)
    type: integer
  feed_stage:
    description: main feed stage
    type: integer
  n_stages:
    description: equilibrium stages, 1..N top to bottom
    type: integer
  pressure_profile:
    description: top pressure or per-stage profile, Pa
    type: number
  pumparounds:
    description: '[{name, draw_stage, return_stage, flow_mol_s, duty_W | return_T_K}]'
    type: array
  reboiler:
    description: kettle | none
    type: string
  side_draw:
    description: '{stage, phase (liquid|vapor), flow_mol_s}; one draw, one port'
    type: object
  specs:
    description: one spec per tear, as the column row
    type: object
  stage_heaters:
    description: '[{stage, duty_W}], duty_W > 0 heats the stage, < 0 cools it; never
      on a condenser or kettle stage'
    type: array
required:
- n_stages
- condenser
- reboiler
- feed_stage
- specs
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 6
- Seader, Henley & Roper 3rd ed., eq. 10-4 (stage heat duty Q_j)

> The MESH extensions the S0 crude column builds on (plan §2b). V1 gap — provisional without a case; covered by a stage-by-stage audit and reductions to the plain column (tests/units/column_shortcut/test_column_extensions.py). Side strippers and the condenser decant are not here: the column refuses them.
