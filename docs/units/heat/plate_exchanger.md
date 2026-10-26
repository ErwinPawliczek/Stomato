# Plate exchanger (`plate_exchanger`)

Family: **heat** · P&ID symbol: `PHE`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `hot_in` | yes | hot-side feed (liquid service) |
| inlet | `cold_in` | yes | cold-side feed |
| outlet | `hot_out` | yes | cooled hot outlet |
| outlet | `cold_out` | yes | warmed cold outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.exchangers:PlateExchanger` | exactly one of duty_W / hot_T_out / cold_T_out; min-approach duty bisection, pinch check and LMTD/UA reported |
| R1 | provisional | `ngdesign.units.heat.plate_exchanger_r1:PlateExchangerR1` | rating — Martin 1996 VDI Heat Atlas N6 chevron correlations (explicit 1/sqrt(f) with the Konakov branch, Nu = 0.122 Pr^1/3 (f Re^2 sin 2phi)^0.374), 1.4-velocity-head port loss, counterflow e-NTU on enthalpies |

### R0 parameters

```yaml
properties:
  cold_T_out:
    description: cold outlet temperature spec, K
    type: number
  dP_cold:
    description: cold-side pressure drop, Pa
    type: number
  dP_hot:
    description: hot-side pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of duty_W/hot_T_out/cold_T_out)
    type: number
  hot_T_out:
    description: hot outlet temperature spec, K
    type: number
  min_approach_K:
    description: solve the duty for this minimum approach, K
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  R_f_cold_m2K_W:
    description: cold-side fouling, m2 K/W, default 0
    type: number
  R_f_hot_m2K_W:
    description: hot-side fouling, m2 K/W, default 0
    type: number
  allow_extrapolation:
    description: rate outside Re 200-1e4 and flag correlation_in_range 0, default
      false
    type: boolean
  amplitude_m:
    description: plate corrugation amplitude, m (half the channel gap)
    type: number
  chevron_angle_deg:
    description: chevron angle from the flow axis, deg, in (10, 80)
    type: number
  correlation:
    description: film-correlation switch, default martin
    enum:
    - martin
    - kumar
    type: string
  k_plate_W_mK:
    description: plate conductivity, W/(m K), default 16 (stainless)
    type: number
  n_plates:
    description: total plate count, integer >= 3 (both fluids flowing)
    type: number
  plate_length_m:
    description: single-plate effective length, m
    type: number
  plate_thickness_m:
    description: plate thickness, m, default 6e-4
    type: number
  plate_width_m:
    description: single-plate width, m
    type: number
  port_diameter_m:
    description: port (maldistribution) diameter, m
    type: number
  wavelength_m:
    description: chevron corrugation wavelength, m
    type: number
required:
- amplitude_m
- wavelength_m
- chevron_angle_deg
- plate_width_m
- plate_length_m
- port_diameter_m
- n_plates
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 4

> No V1 worked case: no single-exchanger printed example with complete printed inputs was located in accessible copies this round (the Kakaç & Liu duty example and the Perry Sect. 11 candidates were checked but not transcribed; Smith Table 16.1 is a network table, not one exchanger). The Smith Table 16.1 water-water streams are covered by the closed-form CP*ΔT test in tests/units/heat/test_exchangers.py; a V1 case needs a printed example with both feeds, an outlet spec and a printed duty/outlet. R1 V1 gap: the R1 verification is carried by the spec's closed-form anchors (friction, Nusselt, h, ΔP and U to 1e-8 relative), the geometry refusals and the R0-reduction identity (R0 replay of the R1 duty to 1e-10); no printed plate-exchanger example with complete geometry, feeds and printed duty/outlet was located, so no R1 V1 case is recorded. Sources searched: the spec's V1 candidate Kakaç, Liu & Pramuanjaroenkij, Heat Exchangers, 3rd ed., ch. 10 (their gasketed-plate rating examples are Kumar-correlation water-water cases with plate geometry and h/U/duty printed, but the accessible copies carry worked solutions as exercise answers or partial tables only); VDI Heat Atlas 2nd ed. N6 (no worked numerical example); Wang, Sundén & Manglik, Plate Heat Exchangers (2007) (design charts, no end-to-end printed example). The VDI N6 equations are pinned by the anchors, which ht's variant='VDI' reproduces only to ~5e-6 relative.
