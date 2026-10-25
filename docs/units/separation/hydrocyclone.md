# Hydrocyclone / cyclone (`hydrocyclone`)

Family: **separation** · P&ID symbol: `CYC`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | slurry/gas feed |
| outlet | `overflow` | yes | fine stream |
| outlet | `underflow` | yes | coarse stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.hydrocyclone:Hydrocyclone` | per-component split spec — the underflow is the spec, not a correlation constant; the overflow leaves at P_in - dP, the underflow at P_in. Evidence gap — Perry Sect. 18 cut-size sizing is R1, so no worked example validates a cut size at R0 (V0 self-consistency only). |
| R1 | provisional | `ngdesign.units.separation.hydrocyclone_r1:HydrocycloneR1` | Lapple cut size (H3), grade efficiency (H4), Rosin-Rammler overall efficiency by 64-point Gauss-Legendre (H5) and Shepherd-Lapple pressure drop (H6); the split is delegated to R0 with the computed fractions. Barth's static-particle model is not part of R1 — the row names "Lapple / Barth", R1 implements Lapple only. Q uses the slurry approximation (total mass flow over the continuous-fluid density). |

### R0 parameters

```yaml
properties:
  dP:
    description: pressure drop, Pa; applied to the overflow outlet
    minimum: 0
    type: number
  underflow_fractions:
    description: component id to the fraction of its molar flow sent to the underflow;
      unnamed components go entirely to the overflow
    type: object
type: object
```

### R1 parameters

```yaml
properties:
  K_inlet:
    description: Shepherd-Lapple inlet constant; default 16 (tangential)
    exclusiveMinimum: 0
    type: number
  N_e:
    description: effective turns; default (Lb + Lc/2)/H
    exclusiveMinimum: 0
    type: number
  body_length_m:
    description: cylinder length Lb, m
    exclusiveMinimum: 0
    type: number
  cone_length_m:
    description: cone length Lc, m
    exclusiveMinimum: 0
    type: number
  dP:
    description: overflow pressure drop, Pa; default Shepherd-Lapple
    minimum: 0
    type: number
  d_rr_m:
    description: Rosin-Rammler characteristic size, m
    exclusiveMinimum: 0
    type: number
  fluid_underflow_fraction:
    description: fluid flow split to the underflow
    exclusiveMaximum: 1
    minimum: 0
    type: number
  fluid_viscosity_Pa_s:
    description: fluid viscosity override, Pa s
    exclusiveMinimum: 0
    type: number
  inlet_height_m:
    description: inlet height H, m
    exclusiveMinimum: 0
    type: number
  inlet_width_m:
    description: inlet width W, m
    exclusiveMinimum: 0
    type: number
  n_rr:
    description: Rosin-Rammler spread
    exclusiveMinimum: 0
    type: number
  outlet_diameter_m:
    description: vortex finder diameter De, m
    exclusiveMinimum: 0
    type: number
  particle_components:
    description: component ids forming the particles/droplets
    items:
      type: string
    minItems: 1
    type: array
  particle_density_kg_m3:
    description: particle density, kg/m3
    exclusiveMinimum: 0
    type: number
  particle_diameter_m:
    description: monodisperse particle diameter, m
    exclusiveMinimum: 0
    type: number
required:
- particle_components
- particle_density_kg_m3
- inlet_width_m
- inlet_height_m
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 6

> R0 split spec implemented; deoiling example with 95 % water to the underflow. R1 V1 gap — no verifiable printed copy of the candidate sources (Cooper & Alley, Air Pollution Control, Ch. 4 Lapple worked example; Perry's 8th ed. Sect. 17 cyclone example) was found online. A Dartmouth ENGS-37 lecture adaptation of the Cooper & Alley example (cushman.host.dartmouth.edu/courses/engs37/Cyclones.pdf, p. 10) prints D, Q, rho_p, the size distribution, N = 6, v_i = 20 m/s, d_pc = 5.79 um and the per-size efficiency table, but not the fluid viscosity or air density the example used, so its d50 anchor cannot be transcribed without reconstructing inputs. Searched 2026-10-25; R1 ships provisional on its closed-form (CF1-CF5) and R0-identity tests.
