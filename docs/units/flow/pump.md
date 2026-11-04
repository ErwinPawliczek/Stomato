# Pump (`pump`)

Family: **flow** · P&ID symbol: `P`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | liquid feed |
| outlet | `outlet` | yes | pressurised liquid (PS flash) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.pump:Pump` | ΔP/outlet P with efficiency; PS flash on the outlet |
| R1 | provisional | `ngdesign.units.flow.pump_r1:PumpR1` | curve (head/efficiency vs flow, PCHIP, affinity laws) and NPSHa check; delegates the outlet to R0 |

Sizer plugin: `pump`

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  eta:
    description: pump efficiency in (0, 1], default 0.65
    type: number
required:
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  curve:
    properties:
      efficiency:
        description: efficiency at each flow point, (0, 1]
        items:
          type: number
        type: array
      flow_m3_s:
        description: curve flow points, m3/s, strictly increasing
        items:
          type: number
        type: array
      head_m:
        description: head at each flow point, m
        items:
          type: number
        type: array
      npsh_required_m:
        description: NPSHr at each flow point, m
        items:
          type: number
        type: array
    required:
    - flow_m3_s
    - head_m
    type: object
  eta:
    description: constant efficiency when the curve has none, (0, 1]
    type: number
  friction_head_m:
    description: suction friction head, m, default 0
    type: number
  npsh_check:
    description: default refuse
    enum:
    - refuse
    - report
    type: string
  speed_ratio:
    description: N / N_curve for the affinity laws, default 1.0
    type: number
  static_head_m:
    description: suction static head, m, default 0
    type: number
required:
- curve
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-pump-gpsa-12-1` | R0 | `power_W` | 17002 | 17013.8 | rel 0.0022 | pass |
| `V1-pump-svna-ex7-10` | R0 | `power_W` | 11570 | 11567 | abs 5 | pass |
| `V1-pump-svna-ex7-10` | R0 | `outlet.outlet.T` | 319.12 | 319.129 | abs 0.005 | assessed miss |

- `V1-pump-gpsa-12-1`: GPSA Engineering Data Book, 13th ed. (FPS), Section 12 Pumps & Hydraulic Turbines, Example 12-1, transcribed from the publisher's official calculation workbook (https://www.gpamidstream.org/wp-content/uploads/2025/08/DBCalculations-13thEdition-Section12.xlsx, sheet "Example 12-1", retrieved 2026-11-04): liquid propane at its bubble point pumped from a 200 psia reflux drum to a 220 psia depropanizer, 360 gpm maximum, 100 degF, SG 0.485; absolute total pressure at pump suction ATPS = 188.8 psig (185.3 + 4.2 static - 0.5 piping - 0.2 valves), at discharge 250.0 psig; dP = 61.2 psi, H = 291.7 ft, required H with 10% safety factor = 320.8 ft; efficiency from Fig. 12-7 e = 0.62; hyd hp = 360 x 320.8 x 0.485 / 3960 = 14.1; bhp = 14.1 / 0.62 = 22.8 (cell display 0.0). The book's bhp depends on the feed only through Q x dP (Q H SG / 3960 = Q dP / 1714), so the feed is the printed 360 gpm at the suction state (310.928 K, 188.8 psig = 1.40308 MPa abs): 243.0 mol/s at the package's 471.78 kg/m3. The pump is set to the required (safety-factored) head as a pressure rise, 1.1 x 61.2377 psi = 67.3614 psi = 464,438 Pa, at the printed e = 0.62.
- `V1-pump-svna-ex7-10`: Smith, Van Ness, Abbott, Swihart, Introduction to Chemical Engineering Thermodynamics, 9th ed., McGraw Hill 2022 (archive.org item text-book-introduction-to-chemical-engineering-thermodynamics-9e-by-j-m-smith, full text read 2026-11-04), Example 7.10, p. 296-297: water at 45 C and 10 kPa pumped adiabatically to 8600 kPa at pump efficiency 0.75; saturated-liquid V = 1010 cm3/kg, beta = 425e-6 1/K, Cp = 4.178 kJ/kg K; Ws(isentropic) = 8.676 kJ/kg, Ws = dH = 11.57 kJ/kg, dT = 0.97 K. 1 kg/s basis (55.50843 mol/s). Tolerances: the printed 0.01 kJ/kg and 0.01 K, fixed before the run.
  - assessed: Power passes (11,567 W, -0.026%). Outlet 319.129 K misses the printed 319.12 +/- 0.005 K by 0.009 K: the book's dT = 0.97 K comes from the constant- property formula Eq. (7.25) with saturated-liquid V, beta and Cp at 45 C, while the unit's PH flash integrates IAPWS-95 along the actual compression. The difference is the book's linearisation; the power, the level's main output, matches.

## References

- docs/unit-catalogue-plan.md §2 U-B 1

> shaft power currently inlined in the unit; the pump_power correlation plugin exists. R1 V1 gap - no open worked example printing a full curve, fluid state and resulting P_out or NPSHa was found or searched for in this pass; provisional on the spec hand calculations and the exact R0 delegation.
