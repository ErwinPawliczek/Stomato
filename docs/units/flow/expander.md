# Expander / turbine (`expander`)

Family: **flow** · P&ID symbol: `T`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | gas feed |
| outlet | `gas_out` | yes | expanded gas (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.expander:Expander` | isentropic expansion with power recovery |
| R1 | provisional | `ngdesign.units.flow.expander_r1:ExpanderR1` | performance map (eta vs u/c0, PCHIP, no extrapolation) driving the R0 expansion |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta_isentropic:
    description: isentropic efficiency in (0, 1], default 0.8
    type: number
required:
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  flow_max_m3_s:
    description: flow-capacity upper limit, m3/s (optional)
    type: number
  flow_min_m3_s:
    description: flow-capacity lower limit, m3/s (optional)
    type: number
  map:
    properties:
      efficiency:
        description: isentropic efficiency in (0, 1] at each velocity_ratio
        items:
          type: number
        type: array
      velocity_ratio:
        description: strictly increasing u/c0 points
        items:
          type: number
        type: array
    required:
    - velocity_ratio
    - efficiency
    type: object
  rotor_diameter_m:
    description: rotor tip diameter, m
    type: number
  speed_rpm:
    description: shaft speed, rpm
    type: number
required:
- P_out
- rotor_diameter_m
- speed_rpm
- map
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-expander-svna-ex7-6` | R0 | `power_W` | -955600 | -956218 | abs 50 | assessed miss |
| `V1-expander-svna-ex7-6` | R0 | `outlet.gas_out.vapor_fraction` | 0.9378 | 0.938205 | abs 5e-05 | assessed miss |
| `V1-expander-perry-ex4-6` | R0 | `power_W` | -204000 | -204695 | abs 500 | assessed miss |

- `V1-expander-svna-ex7-6`: Smith, Van Ness, Abbott, Swihart, Introduction to Chemical Engineering Thermodynamics, 9th ed., McGraw Hill 2022 (archive.org item text-book-introduction-to-chemical-engineering-thermodynamics-9e-by-j-m-smith, full text read 2026-11-04), Example 7.6, p. 287-288: steam turbine, inlet 8600 kPa and 500 C, discharge 10 kPa, turbine efficiency 0.75; steam tables H1 = 3391.6, S1 = 6.6858, isentropic x2' = 0.8047, dH = -955.6 kJ/kg, H2 = 2436.0 kJ/kg, x2 = 0.9378. 1 kg/s basis (55.50843 mol/s; the molar vapour fraction of pure water equals the mass quality). Tolerances: the printed 0.1 kJ/kg and 4-decimal quality, fixed before the run.
  - assessed: Measured power -956,218 W (-956.22 kJ/kg, +0.065% on -955.6) and outlet quality 0.938205 (book 0.9378). CoolProp 8.0.0 IAPWS-95 on the same path gives H1 = 3392.26 kJ/kg (book 3391.6), dH = -956.22 kJ/kg and x2 = 0.938205, identical to the unit. The miss is the book's steam-table values and interpolation, not the expansion calculation; level stays provisional.
- `V1-expander-perry-ex4-6`: Perry's Chemical Engineers' Handbook, 9th ed., McGraw-Hill 2019, Section 4, Example 4-6 "Turbine Process Design" (archive.org item perrys-chemical-engineers-handbook-9th-edition, full text read 2026-11-04): steam expanded from 500 C and 1.4 MPa to 0.6 MPa at 75% efficiency, Elliott & Lira steam tables H1 = 3474.8 kJ/kg, S1 = 7.6047 kJ/kg K, H2' = 3202.8 kJ/kg, W = (3202.8 - 3474.8)(0.75) = -204 kJ/kg. 1 kg/s basis (55.50843 mol/s). Tolerance: the printed integer kJ/kg (+/-0.5 kJ/kg), fixed before the run.
  - assessed: Measured power -204,695 W (-204.70 kJ/kg) against the printed -204 +/- 0.5. CoolProp 8.0.0 IAPWS-95 gives H1 = 3474.78 kJ/kg (book 3474.8) and dH = -204.70 kJ/kg, identical to the unit; the book's interpolated H2' = 3202.8 kJ/kg in the Elliott & Lira tables sits 0.9 kJ/kg above the IAPWS-95 isentrope. Table-interpolation difference, not a unit error; level stays provisional.

## References

- docs/unit-catalogue-plan.md §2 U-B 4

> the hydraulic turbine / pressure-recovery line (plan U-B 12) is covered by this row — isentropic expansion recovering shaft power — not a separate row. R1 V1 gap (PR 297) — no accessible source prints a full u/c0 performance map together with the inlet state and the resulting outlet; searched Whitfield & Baines, Design of Radial Turbomachines (1990) ch. 7 (eta-vs-U/C0 is figure/curve data), Balje, Turbomachines (1981) ch. 3, Perry's 9th ed. sect. 10 (expander sizing curves, no worked example with a printed outlet state), GPSA Data Book sect. 13 (public GPA example spreadsheets cover Example 13-1 compressor work, not a turboexpander with printed map and states), and Campbell, Gas Conditioning and Processing vol. 2 (expander chapter). The level ships provisional, covered by the closed-form, identity and refusal tests.
