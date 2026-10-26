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
| R1 | provisional | `ngdesign.units.heat.multi_stream_r1:MultiStreamR1` | common-wall BVP over per-stream T(H) tables with given layer hA; no T_out specs, every outlet solved by the coupled balances; reports minimum approach, wall-mediated UA and BVP nodes; per-port duties in R0 signs (hot releases, cold absorbs) |
| R2 | provisional | `ngdesign.units.heat.multi_stream_r2:MultiStreamR2` | zoned plate-fin rating with phase change: per-layer offset-strip-fin geometry (Manglik-Bergles j, fin/surface efficiency), a zone loop that recomputes h at the zone-mean state (single phase, or ht.Shah condensation / ht.Liu_Winterton boiling through D_h as a stated approximation) and re-solves the common-wall BVP with piecewise hA |

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
    description: cold_in_1 pressure drop, Pa (default 0)
    type: number
  dP_cold_in_2:
    description: cold_in_2 pressure drop, Pa (default 0)
    type: number
  dP_hot_in_1:
    description: hot_in_1 pressure drop, Pa (default 0)
    type: number
  dP_hot_in_2:
    description: hot_in_2 pressure drop, Pa (default 0)
    type: number
  hA_cold_in_1_W_K:
    description: layer conductance of cold_in_1, W/K (required for every active stream)
    type: number
  hA_cold_in_2_W_K:
    description: layer conductance of cold_in_2, W/K (required when active)
    type: number
  hA_hot_in_1_W_K:
    description: layer conductance of hot_in_1, W/K (required for every active stream)
    type: number
  hA_hot_in_2_W_K:
    description: layer conductance of hot_in_2, W/K (required when active)
    type: number
type: object
```

### R2 parameters

```yaml
properties:
  dP_cold_in_1:
    description: cold_in_1 pressure drop, Pa (default 0)
    type: number
  dP_cold_in_2:
    description: cold_in_2 pressure drop, Pa (default 0)
    type: number
  dP_hot_in_1:
    description: hot_in_1 pressure drop, Pa (default 0)
    type: number
  dP_hot_in_2:
    description: hot_in_2 pressure drop, Pa (default 0)
    type: number
  fin_height_cold_in_1_m:
    description: cold_in_1 fin height, m (required for every active stream)
    type: number
  fin_height_cold_in_2_m:
    description: cold_in_2 fin height, m (required for every active stream)
    type: number
  fin_height_hot_in_1_m:
    description: hot_in_1 fin height, m (required for every active stream)
    type: number
  fin_height_hot_in_2_m:
    description: hot_in_2 fin height, m (required for every active stream)
    type: number
  fin_spacing_cold_in_1_m:
    description: cold_in_1 fin spacing, m (required for every active stream)
    type: number
  fin_spacing_cold_in_2_m:
    description: cold_in_2 fin spacing, m (required for every active stream)
    type: number
  fin_spacing_hot_in_1_m:
    description: hot_in_1 fin spacing, m (required for every active stream)
    type: number
  fin_spacing_hot_in_2_m:
    description: hot_in_2 fin spacing, m (required for every active stream)
    type: number
  fin_thickness_cold_in_1_m:
    description: cold_in_1 fin thickness, m (required for every active stream)
    type: number
  fin_thickness_cold_in_2_m:
    description: cold_in_2 fin thickness, m (required for every active stream)
    type: number
  fin_thickness_hot_in_1_m:
    description: hot_in_1 fin thickness, m (required for every active stream)
    type: number
  fin_thickness_hot_in_2_m:
    description: hot_in_2 fin thickness, m (required for every active stream)
    type: number
  k_fin_W_mK:
    description: fin thermal conductivity, W/(m K) (default 180)
    type: number
  layer_width_m:
    description: shared layer width (fin gap direction), m
    type: number
  length_m:
    description: shared exchanger length, m
    type: number
  n_zones:
    description: zone count for the zone loop (default 20)
    type: integer
  strip_length_cold_in_1_m:
    description: cold_in_1 offset-strip length, m (required for every active stream)
    type: number
  strip_length_cold_in_2_m:
    description: cold_in_2 offset-strip length, m (required for every active stream)
    type: number
  strip_length_hot_in_1_m:
    description: hot_in_1 offset-strip length, m (required for every active stream)
    type: number
  strip_length_hot_in_2_m:
    description: hot_in_2 offset-strip length, m (required for every active stream)
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-C 6

> No V1 worked case: Smith Table 16.2 (the four-stream LNG-cold-box basis) needs 7.5 MW of hot utility that the utility-free R0 unit does not model, and every single-balance arrangement of the four streams crosses (verified by hand cascade). The Smith streams 1+3 two-stream balance is covered by the closed-form test in tests/units/heat/test_multi_stream.py; outlet ports are positional, not mirrored inlet names. R1 V1 gap (searched 2026-10-25): Haseler (1983), Shah & Sekulic, Fundamentals of Heat Exchanger Design (2003) ch. 8-9, and the ALPEMA standards print no worked multi-stream rating. The R1 evidence is the constant-capacity-rate epsilon-NTU reduction, an independently hand-computed two-hot/one-cold case (not a printed source), and the R0 identity test in tests/units/heat/test_multi_stream_r1.py. R2 V1 gap (searched 2026-10-25): the printed sources checked are Shah & Sekulic (2003) ch. 9 and Kays & London, Compact Heat Exchangers 3rd ed. - single-phase core sizing/checking and offset-strip-fin surface data, no multi-stream plate-fin rating with printed outlet states. The R2 evidence is the closed-form Manglik-Bergles j/f values, the fin/surface efficiency closed forms, and the R2-R1 identity test (given hA reproduces the R1 result) in tests/units/heat/test_multi_stream_r2.py.
