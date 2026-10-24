# Product blender (`blending`)

Family: **refining** · P&ID symbol: `BL`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `component_in_1` | yes | first blendstock feed |
| inlet | `component_in_2` | yes | second blendstock feed |
| inlet | `component_in_3` | yes | third blendstock feed (zero-flow when unused) |
| outlet | `blend_out` | yes | blended product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.blending:Blender` | adiabatic PH mix (duty 0) plus property indices — RVP by the Gary-Handwerk-Kaiser/Chevron index RVP^1.25 on a volume basis, sulfur mass-weighted, octane and cetane linear by volume (documented R0 simplification; real blending is interactive), one D86 point by volume-average T (R0); every rule cited in the adapter (spec U-H1, three declared inlets, unused ports zero-flow) |

### R0 parameters

```yaml
properties:
  P:
    description: blend pressure (Pa abs, default the first inlet's)
    type: number
  properties:
    description: per-inlet-port blendstock properties {rvp_psi, sulfur_wt_ppm, ron,
      cetane_index, d86_point_k}; an index is reported only when every flowing inlet
      declares it
    type: object
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 12

> V1 gap — provisional without a case. The GHK 5th ed. ch. 12 printed RVP blending example could not be re-read from an open copy at re-review time, and the former V2106 pin was index arithmetic on its own input values (with an invented reformate stand-in), so it was withdrawn; the RVP/sulfur/ RON index arithmetic is covered by closed-form tests in tests/units/refining/test_separation.py.
