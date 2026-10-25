# Multi-stream exchanger (LNG cold box) (`multi_stream`)

Family: **heat** · P&ID symbol: `MS`

Rigour ladder: R0 provisional, R1 provisional, R2 planned

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
| R2 | planned | — | zoned with phase change |

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

## References

- docs/unit-catalogue-plan.md §2 U-C 6

> No V1 worked case: Smith Table 16.2 (the four-stream LNG-cold-box basis) needs 7.5 MW of hot utility that the utility-free R0 unit does not model, and every single-balance arrangement of the four streams crosses (verified by hand cascade). The Smith streams 1+3 two-stream balance is covered by the closed-form test in tests/units/heat/test_multi_stream.py; outlet ports are positional, not mirrored inlet names. R1 has no printed worked rating either: the evidence base is the closed-form constant-capacity-rate epsilon-NTU reduction, the two-hot/one-cold printed reference, and the R0 identity test in tests/units/heat/test_multi_stream_r1.py - the V1 evidence gap stands at R1.
