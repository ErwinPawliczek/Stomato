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

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-compressor-svna-ex7-8` | R0 | `power_W` | 284500 | 283805 | abs 50 | assessed miss |
| `V1-compressor-svna-ex7-8` | R0 | `outlet.outlet.T` | 519.25 | 518.722 | abs 0.05 | assessed miss |

- `V1-compressor-svna-ex7-8`: Smith, Van Ness, Abbott, Swihart, Introduction to Chemical Engineering Thermodynamics, 9th ed., McGraw Hill 2022 (archive.org item text-book-introduction-to-chemical-engineering-thermodynamics-9e-by-j-m-smith, full text read 2026-11-04), Example 7.8, p. 292-293: saturated-vapour steam at 100 kPa (tsat 99.63 C) compressed adiabatically to 300 kPa at compressor efficiency 0.75; steam tables H1 = 2675.4, (dH)S = 213.4, dH = Ws = 284.5 kJ/kg, H2 = 2959.9 kJ/kg, T2 = 246.1 C, S2 = 7.5019 kJ/kg K. 1 kg/s basis (55.50843 mol/s); the feed sits 0.03 K above the printed tsat so the flash returns the saturated vapour. Tolerances: the printed 0.1 kJ/kg and 0.1 C, fixed before the run.
  - assessed: Measured power 283,805 W (283.80 kJ/kg, -0.24% on the printed 284.5) and outlet 518.722 K (245.57 C, -0.53 K on 246.1 C). The unit reproduces the IAPWS-95 reference: CoolProp 8.0.0 (IAPWS-95) gives h1 = 2674.95 kJ/kg (book 2675.4), (dH)S = 212.82 kJ/kg (book 213.4), dH = 283.76 kJ/kg and T2 = 245.49 C on the same path; the 0.05 K of superheat on the feed accounts for the rest. The miss is the book's older steam-table values and linear interpolation, not the compressor calculation; recorded, level stays provisional.

## References

- docs/unit-catalogue-plan.md §2 U-B 2

> multi-section compression with intercooling is its own flow row (compression_train), not a level of this row. V1 gap recorded in specs/backend/units/compressor.md — no printed Schultz polytropic example with reproducible inputs/results has been verified (ASME PTC 10-1997 appendix, Schultz 1962, Ludwig vol. 3 ch. 15, Perry's 9th ed. §10 all unexamined); R1 is anchored by closed-form tests against an independent bisection script instead.
