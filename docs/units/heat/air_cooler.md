# Air cooler (`air_cooler`)

Family: **heat** · P&ID symbol: `AC`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | process feed |
| outlet | `outlet` | yes | cooled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat_exchange:HeatExchanger` | approach / duty spec |
| R1 | provisional | `ngdesign.units.heat.air_cooler_r1:AirCoolerR1` | rating (Briggs-Young air side on the bare-area basis, ESDU 86022 air dP, duct_h tube side, brentq duty solve with Ft_aircooler; fan power reported in info, the air side is not a port) |

Sizer plugin: `air_cooler`

### R0 parameters

```yaml
properties:
  T_out:
    description: outlet temperature spec, K
    type: number
  dP:
    description: pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of T_out/duty_W)
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  R_f_tube_m2K_W:
    description: tube-side fouling resistance, m2 K/W, default 0
    type: number
  air_P_Pa:
    description: air-side pressure, Pa, default 101325
    type: number
  air_T_K:
    description: air inlet temperature, K
    type: number
  air_composition:
    description: air mole fractions, default N2 0.79 / O2 0.21
    type: object
  air_mass_flow_kg_s:
    description: total air mass flow, kg/s
    type: number
  allow_extrapolation:
    description: rate outside the Briggs-Young Re window (1000, 8000), flagged briggs_young_in_range,
      default false
    type: boolean
  bundles_per_bay:
    description: bundles per bay, default 1
    type: integer
  fan_efficiency:
    description: fan efficiency in (0, 1]
    type: number
  fin_density_per_m:
    description: 'fins per metre (alternative: fin_interval_m)'
    type: number
  fin_height_m:
    description: 'fin height, m (alternative: fin_diameter_m)'
    type: number
  fin_thickness_m:
    description: fin thickness, m
    type: number
  k_fin_W_mK:
    description: fin conductivity, W/(m K), default 205
    type: number
  k_wall_W_mK:
    description: tube wall conductivity, W/(m K), default 45
    type: number
  parallel_bays:
    description: parallel bays, default 1
    type: integer
  pitch_normal_m:
    description: staggered pitch normal to flow, m
    type: number
  pitch_parallel_m:
    description: 'staggered pitch parallel to flow, m (alternative pitch spec: pitch_m
      with angle_deg)'
    type: number
  roughness_m:
    description: absolute roughness, m, default 4.5e-5
    type: number
  tube_OD_m:
    description: tube outside diameter, m
    type: number
  tube_length_m:
    description: bare tube length, m
    type: number
  tube_passes:
    description: tube passes; supported pairs (1, 1-4), (2, 2), (2, 4), (3, 3), (4,
      4) and passes = rows > 4
    type: integer
  tube_rows:
    description: tube rows deep
    type: integer
  tube_wall_m:
    description: tube wall thickness, m
    type: number
  tubes_per_row:
    description: tubes per row
    type: integer
required:
- tube_rows
- tube_passes
- tubes_per_row
- tube_length_m
- tube_OD_m
- tube_wall_m
- fin_thickness_m
- fin_height_m
- fin_density_per_m
- pitch_parallel_m
- pitch_normal_m
- air_T_K
- air_mass_flow_kg_s
- fan_efficiency
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 3

> R1 is rated on the ht AirCooledExchanger docstring bundle basis (the S1 natural-gas slice E-101 geometry, plan §2b). V1 gap: searched GPSA EDB Sec. 10, Serth 2nd ed. Ch. 12, Kern & Kraus 1972 Ch. 12 - no printed air-cooler rating example with complete inputs was accessible, so the closed-form Briggs-Young, ESDU and fan-power checks and the R0-reduction identity carry the R1 verification.
