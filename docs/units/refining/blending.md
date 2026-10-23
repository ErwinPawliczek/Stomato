# Gasoline / diesel blending (`blending`)

Family: **refining** · P&ID symbol: `BL`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `component_in` | yes | blendstock feed (multiple via params) |
| outlet | `blend_out` | yes | blended product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | linear blend of component properties — shares the mixer adapter (linear blend) |
| R1 | planned | — | blend indices (RON/MON, RVP, pour) — the cloud_point and pour_point plugins exist |

## References

- docs/unit-catalogue-plan.md §2 U-H 9

> R0 shares the mixer adapter (linear blend); R1 index work is U-H's thread.
