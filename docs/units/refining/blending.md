# Product blender (`blending`)

Family: **refining** · P&ID symbol: `BL`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `component_in` | yes | blendstock feed (multiple via params) |
| outlet | `blend_out` | yes | blended product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | volume/mass blending with property indices (RVP, octane, cetane, sulfur, D86) |

## References

- docs/unit-catalogue-plan.md §2 U-H 12

> roadmap; the R0 blend shares the mixer adapter for the linear part, the index work (cloud_point and pour_point plugins exist) is U-H's thread.
