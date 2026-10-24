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

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2106` | R0 | `info.rvp_psi` | 31.4449 | 31.4449 | rel 0.001 | pass |
| `V2106` | R0 | `info.ron` | 91.0826 | 91.0826 | rel 0.001 | pass |
| `V2106` | R0 | `info.sulfur_wt_ppm` | 0.8052 | 0.805211 | rel 0.001 | pass |
| `V2106` | R0 | `duty_W` | 0 | 0 | abs 1e-06 | pass |

- `V2106`: Gary, Handwerk & Kaiser, Petroleum Refining: Technology and Economics, 5th ed., ch. 12 blending indices: RVP^1.25 on a volume basis, sulfur linear on mass, octane linear by volume (the documented R0 simplification). Component values from Jechura, Product Blending & Optimization Considerations (CBEN 409, Colorado School of Mines): nC4 RVP 51.0 psi / RON 95.0; nC5 RVP 15.0 psi / RON 86.0; reformate stand-in (C6+ carrier) RVP 2.8 psi / RON 92.5. Expected values recomputed independently from the component MW/sg of the bank

## References

- docs/unit-catalogue-plan.md §2 U-H 12

> roadmap; the R0 blend shares the mixer adapter for the linear part, the index work (cloud_point and pour_point plugins exist) is U-H's thread.
