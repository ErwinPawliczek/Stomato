# Divided-wall / Petlyuk column (`divided_wall`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | feed |
| outlet | `distillate` | yes | light product |
| outlet | `side_product` | yes | middle product |
| outlet | `bottoms` | yes | heavy product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column.divided_wall:DividedWallR2` | one simultaneous MESH solve over the whole shell on the column core's stage graph (graph_ns) - common top, main side, common bottom as the main cascade, the prefractionator a section linked by the split liquid, its top-vapour return, its bottom liquid and the split vapour; the vapour split is a Newton unknown closed by equal pressure drop across the two sides (turbulent dry-bed dP ~ rho_V u^2, Stichlmair, Bravo & Fair 1989; split set by the wall position, Dejanovic et al. 2010) or specified; seeded from the wall-free shell on the same specs |

### R2 parameters

```yaml
additionalProperties: false
properties:
  feed_stage:
    description: prefractionator stage of the feed, 1..n_prefractionator
    minimum: 1
    type: integer
  liquid_split:
    description: fraction of the liquid leaving the stage above the wall sent to the
      prefractionator
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
  n_bottom:
    description: common stripping stages below the wall, the kettle reboiler last
    minimum: 2
    type: integer
  n_main_wall:
    description: side-draw-side wall stages
    minimum: 1
    type: integer
  n_prefractionator:
    description: feed-side wall stages (the prefractionator)
    minimum: 1
    type: integer
  n_top:
    description: common rectifying stages above the wall (stage 1 under the total
      condenser)
    minimum: 1
    type: integer
  pressure_profile:
    description: main-cascade stage pressures, Pa abs (scalar = uniform; {top, bottom}
      = linear); default feed.P; prefractionator stages interpolate across the wall
    oneOf:
    - exclusiveMinimum: 0
      type: number
    - type: object
  side_draw_rate:
    description: side product, mol/s
    exclusiveMinimum: 0
    type: number
  side_draw_stage:
    description: main-side stage of the liquid side product, 1..n_main_wall
    minimum: 1
    type: integer
  specs:
    description: exactly reflux_ratio and distillate_rate (mol/s)
    type: object
  vapour_split:
    description: fraction of the vapour leaving the stage below the wall sent to the
      prefractionator; omitted = solved from equal pressure drop across the two sides
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
  wall_area_fraction:
    description: prefractionator share of the cross-section, for the equal pressure-drop
      split (default 0.5)
    exclusiveMaximum: 1
    exclusiveMinimum: 0
    type: number
required:
- n_top
- n_prefractionator
- n_main_wall
- n_bottom
- feed_stage
- side_draw_stage
- side_draw_rate
- liquid_split
- specs
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 10
- Dejanovic, Matijasevic & Olujic, Chem. Eng. Process. 49 (2010) 559-580
- Stichlmair, Bravo & Fair, Gas Sep. Purif. 3 (1989) 19-28
- Russell 1983, Comput. Chem. Eng. 7, 571-578

> V1 gap - provisional without a case. Checked by every stage's component balance re-closed from the reported stage flows over the four wall links, the vapour split meeting its pressure-drop equation (and a specified split held exactly), and the symmetric reduction to the plain column (feed above the wall, no side draw, liquid split = area fraction: both wall sides reproduce the plain column's stages) (tests/units/column/test_divided_wall.py). Specs are reflux_ratio + distillate_rate only (the graph Newton's top-vapour mode). Measured limit: the initializer is the plain column's own spec loop, which does not converge on BTX 8 + 12|12 + 8 stages at R = 5 (inside-out and its NS fallback at tears 166.7 / 186.7 mol/s), so that shell is refused there.
