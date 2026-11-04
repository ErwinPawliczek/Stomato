# JT valve (`jt_valve`)

Family: **flow** · P&ID symbol: `V`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | isenthalpic (flash_ph) outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.jt_valve:JTValve` | isenthalpic flash to the outlet pressure |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
required:
- P_out
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-jt-valve-purdue-me200-steam` | R0 | `outlet.outlet.T` | 763.25 | 763.234 | abs 0.05 | pass |
| `V1-jt-valve-svna-sec7-1-steam` | R0 | `outlet.outlet.T` | 561.95 | 561.771 | abs 0.05 | assessed miss |

- `V1-jt-valve-purdue-me200-steam`: Purdue University ME 200 Thermodynamics I lecture notes, Fall 2008, week 7 (https://engineering.purdue.edu/CFDLAB/class/me200/filesFall2008/me200_notes_f08_week7.pdf), p. 6 "Throttling valves", Example 1, read 2026-11-04: a well-insulated valve throttles steam from 8 MPa and 500 C to 6 MPa; h1 = h2 = 3398.3 kJ/kg (steam tables, Table A-6), printed T2 = 490.1 C. Tolerance: the one-decimal print, +/-0.05 K, fixed before the run.
- `V1-jt-valve-svna-sec7-1-steam`: Smith, Van Ness, Abbott, Swihart, Introduction to Chemical Engineering Thermodynamics, 9th ed., McGraw Hill 2022 (archive.org item text-book-introduction-to-chemical-engineering-thermodynamics-9e-by-j-m-smith, full text read 2026-11-04), Sec. 7.1 (throttling processes), text p. 282: steam at 1000 kPa and 300 C throttled to 101.325 kPa, H2 = H1 = 3052.1 kJ/kg, interpolation in the steam tables gives a downstream temperature of 288.8 C. Tolerance: the printed 0.1 C, fixed before the run.
  - assessed: Measured 561.771 K (288.62 C) against the printed 288.8 C. CoolProp 8.0.0 IAPWS-95 gives H1 = 3051.63 kJ/kg (book 3052.1) and the isenthalpic outlet at 101.325 kPa = 288.62 C, identical to the unit. The 0.18 K miss is the book's steam-table values; level status rests on the passing Purdue case.

## References

- docs/unit-catalogue-plan.md §2 U-B 5

> the palette defines no higher level for the JT valve (plan §2 U-B 5).
