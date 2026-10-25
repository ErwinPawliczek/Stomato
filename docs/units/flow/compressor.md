# Centrifugal compressor (`compressor`)

Family: **flow** · P&ID symbol: `C`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas feed |
| outlet | `outlet` | yes | compressed gas (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.compressor:Compressor` | isentropic/polytropic efficiency; PS flash on the outlet |
| R1 | provisional | `ngdesign.units.flow.compressor_r1:CompressorR1` | performance map (head/efficiency vs flow, fan laws, surge/stonewall), Schultz polytropic |

Sizer plugin: `compressor`

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta_isentropic:
    description: isentropic efficiency in (0, 1], default 0.75
    type: number
required:
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  efficiency_basis:
    description: default polytropic
    enum:
    - polytropic
    - isentropic
    type: string
  map:
    properties:
      efficiency:
        description: efficiency at each point, (0, 1]
        items:
          type: number
        type: array
      flow_m3_s:
        description: actual inlet flow points at map speed, m3/s, strictly increasing
        items:
          type: number
        type: array
      head_J_kg:
        description: head at each point, J/kg (basis per efficiency_basis)
        items:
          type: number
        type: array
    required:
    - flow_m3_s
    - head_J_kg
    - efficiency
    type: object
  max_pressure_ratio:
    description: upper bracket for the discharge pressure solve, default 10
    type: number
  speed_ratio:
    description: N / N_map (fan laws), default 1.0
    type: number
  stonewall_flow_m3_s:
    description: stonewall flow at map speed, m3/s, default last map point
    type: number
  surge_flow_m3_s:
    description: surge flow at map speed, m3/s, default first map point
    type: number
required:
- map
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 2

> multi-section compression with intercooling is its own flow row (compression_train), not a level of this row. V1 gap recorded in specs/backend/units/compressor.md — no printed Schultz polytropic example with reproducible inputs/results has been verified (ASME PTC 10-1997 appendix, Schultz 1962, Ludwig vol. 3 ch. 15, Perry's 9th ed. §10 all unexamined); R1 is anchored by closed-form tests against an independent bisection script instead.
