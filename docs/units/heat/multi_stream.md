# Multi-stream exchanger (LNG cold box) (`multi_stream`)

Family: **heat** · P&ID symbol: `MS`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `hot_in_1` | yes | first hot feed (0 = inactive) |
| inlet | `hot_in_2` | no | second hot feed (0 = inactive) |
| inlet | `cold_in_1` | yes | first cold feed (0 = inactive) |
| inlet | `cold_in_2` | no | second cold feed (0 = inactive) |
| outlet | `hot_out_1` | yes | positional outlet for hot_in_1 |
| outlet | `hot_out_2` | yes | positional outlet for hot_in_2 |
| outlet | `cold_out_1` | yes | positional outlet for cold_in_1 |
| outlet | `cold_out_2` | yes | positional outlet for cold_in_2 |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.multi_stream:MultiStreamExchanger` | every active side carries a T_out spec except exactly one balance stream, which absorbs the residual duty; zoned composite pinch check, per-port duties |
| R1 | provisional | `ngdesign.units.heat.multi_stream_r1:MultiStreamR1` | common-wall layer model (Haseler 1983) solved as a BVP over monotone T(H) tables, on given layer conductances; reduces to R0 at its own outlet temperatures |
| R2 | provisional | `ngdesign.units.heat.multi_stream_r2:MultiStreamR2` | zoned plate-fin rating on the R1 common-wall BVP; Manglik and Bergles 1995 single phase, Shah and Liu-Winterton two phase through the channel hydraulic diameter (a tube-correlation approximation); piecewise hA(x); reduces to R1 in one zone at R2's own conductances |

### R0 parameters

```yaml
properties:
  T_out_cold_in_1:
    description: cold_in_1 outlet temperature spec, K
    type: number
  T_out_cold_in_2:
    description: cold_in_2 outlet temperature spec, K
    type: number
  T_out_hot_in_1:
    description: hot_in_1 outlet temperature spec, K
    type: number
  T_out_hot_in_2:
    description: hot_in_2 outlet temperature spec, K
    type: number
type: object
```

### R1 parameters

```yaml
properties:
  dP_cold_in_1:
    description: pressure drop, Pa, default 0
    type: number
  dP_cold_in_2:
    description: pressure drop, Pa, default 0
    type: number
  dP_hot_in_1:
    description: pressure drop, Pa, default 0
    type: number
  dP_hot_in_2:
    description: pressure drop, Pa, default 0
    type: number
  hA_cold_in_1_W_K:
    description: layer conductance of cold_in_1, W/K
    type: number
  hA_cold_in_2_W_K:
    description: layer conductance of cold_in_2, W/K
    type: number
  hA_hot_in_1_W_K:
    description: layer conductance of hot_in_1, W/K
    type: number
  hA_hot_in_2_W_K:
    description: layer conductance of hot_in_2, W/K
    type: number
type: object
```

### R2 parameters

```yaml
properties:
  dP_cold_in_1:
    description: pressure drop, Pa, default 0
    type: number
  dP_cold_in_2:
    description: pressure drop, Pa, default 0
    type: number
  dP_hot_in_1:
    description: pressure drop, Pa, default 0
    type: number
  dP_hot_in_2:
    description: pressure drop, Pa, default 0
    type: number
  fin_height_cold_in_1_m:
    description: offset-strip fin height, m
    type: number
  fin_height_cold_in_2_m:
    description: offset-strip fin height, m
    type: number
  fin_height_hot_in_1_m:
    description: offset-strip fin height, m
    type: number
  fin_height_hot_in_2_m:
    description: offset-strip fin height, m
    type: number
  fin_spacing_cold_in_1_m:
    description: fin spacing, m
    type: number
  fin_spacing_cold_in_2_m:
    description: fin spacing, m
    type: number
  fin_spacing_hot_in_1_m:
    description: fin spacing, m
    type: number
  fin_spacing_hot_in_2_m:
    description: fin spacing, m
    type: number
  fin_thickness_cold_in_1_m:
    description: fin thickness, m
    type: number
  fin_thickness_cold_in_2_m:
    description: fin thickness, m
    type: number
  fin_thickness_hot_in_1_m:
    description: fin thickness, m
    type: number
  fin_thickness_hot_in_2_m:
    description: fin thickness, m
    type: number
  k_fin_W_mK:
    description: fin conductivity, W/(m K), default 180 (aluminium alloy)
    type: number
  layer_width_m:
    description: layer width, m
    type: number
  length_m:
    description: core flow length, m
    type: number
  n_layers_cold_in_1:
    description: layers of cold_in_1
    type: integer
  n_layers_cold_in_2:
    description: layers of cold_in_2
    type: integer
  n_layers_hot_in_1:
    description: layers of hot_in_1
    type: integer
  n_layers_hot_in_2:
    description: layers of hot_in_2
    type: integer
  n_zones:
    description: equal-duty zones, default 20
    type: integer
  strip_length_cold_in_1_m:
    description: offset strip length, m
    type: number
  strip_length_cold_in_2_m:
    description: offset strip length, m
    type: number
  strip_length_hot_in_1_m:
    description: offset strip length, m
    type: number
  strip_length_hot_in_2_m:
    description: offset strip length, m
    type: number
required:
- layer_width_m
- length_m
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 6

> R1 ships provisional on the spec's independent MS1 and MS2 and the reduction to R0; no printed multi-stream rating example was searched for. R2 ships provisional on the spec's Manglik-Bergles, D_h and fin-efficiency values and the reduction to R1; no plate-fin V1 case was searched for. No R0 V1 worked case: Smith Table 16.2 (the four-stream LNG-cold-box basis) needs 7.5 MW of hot utility that the utility-free R0 unit does not model, and every single-balance arrangement of the four streams crosses (verified by hand cascade). The Smith streams 1+3 two-stream balance is covered by the closed-form test in tests/units/heat/test_multi_stream.py; outlet ports are positional, not mirrored inlet names.
