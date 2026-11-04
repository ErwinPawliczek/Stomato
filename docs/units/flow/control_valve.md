# Control valve (`control_valve`)

Family: **flow** · P&ID symbol: `CV`

Rigour ladder: R0 validated, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | throttled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | validated | `ngdesign.units.flow.control_valve:ControlValve` | Cv / outlet P spec, isenthalpic (the cv_liquid correlation plugin exists) |
| R1 | provisional | `ngdesign.units.flow.control_valve_r1:ControlValveR1` | IEC 60534-2-1 sizing/rating through fluids.control_valve, choked flow, inherent characteristic |

### R1 parameters

```yaml
properties:
  Cv_rated:
    description: rated full-travel Cv (US); required in rating mode
    type: number
  D1_m:
    description: upstream pipe ID, m (sizing; all three or none)
    type: number
  D2_m:
    description: downstream pipe ID, m
    type: number
  FL:
    description: liquid pressure-recovery factor, default 0.9
    type: number
  Fd:
    description: valve style modifier, default 1.0
    type: number
  P_out:
    description: 'sizing mode: outlet pressure, Pa'
    type: number
  characteristic:
    description: inherent characteristic, default linear
    enum:
    - linear
    - equal_percentage
    - quick_opening
    type: string
  dP:
    description: 'sizing mode: pressure drop, Pa'
    type: number
  d_m:
    description: valve size, m
    type: number
  mu_gas:
    description: gas viscosity, Pa.s, if the thermo reports none
    type: number
  mu_liquid:
    description: liquid viscosity, Pa.s, if the thermo reports none
    type: number
  opening:
    description: 'rating mode: relative travel in (0, 1]'
    type: number
  rangeability:
    description: equal-percentage rangeability R > 1, default 50
    type: number
  xT:
    description: gas pressure-differential ratio factor, default 0.7
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-control-valve-emerson-propane` | R0 | `info.Cv` | 113.14 | 113.419 | rel 0.005 | pass |
| `V1-control-valve-emerson-propane` | R0 | `info.choked` | 0 | 0 | abs 0 | pass |

- `V1-control-valve-emerson-propane`: Emerson Automation Solutions, Control Valve Handbook, 6th ed. (2019/2023), Chapter 5, section 5.8.4 "Liquid Sizing Sample Problem", pp. 114-115 (https://www.emerson.com/documents/automation/control-valve-handbook-en-3661206.pdf, read 2026-11-04; the equation lines are images, read from the rendered page): liquid propane, q = 800 gpm, P1 = 314.7 psia, P2 = 289.7 psia, dP = 25 psi, T1 = 70 F, rho1/rho0 = 0.50, Pv = 124.3 psia, Pc = 616.3 psia; FF = 0.83, dP_choked = 171 psi > 25 psi (not choked); Cv = 800 / (1.0 x 0.9 sqrt(25/0.5)) = 125.7 with the assumed NPS 3 valve's FP = 0.90. R0 reports the bare-valve Cv (FP = 1): 800 / sqrt(25/0.5) = 113.14 (= 125.7 x 0.90). Feed: 800 gpm at the package's 502.05 kg/m3 (25.34 kg/s = 574.66 mol/s) at 70 F and 314.7 psia. Tolerance 0.5%: the printed two-figure rho1/rho0 = 0.50 (+/-0.005 moves Cv by 0.5%). Re-cited 2026-11-04 (units-a) from the earlier uncited "117.9 x 0.96 = 113.2" (an older edition's FP), expected value corrected to this edition's arithmetic.

## References

- docs/unit-catalogue-plan.md §2 U-B 6

> R0 isenthalpic letdown; ISA liquid Cv is reported when the inlet is liquid and a viscosity is available (PR phase property or a mu_liquid param); IEC 60534 sizing and choked flow are R1. R1 V1 gap - the IEC 60534-2-1 Annex D printed Kv values could not be read from an open copy and the fluids docstring numbers are model output, not valid V1; provisional on the spec hand calculations of eqs. 1-4, 8, 10 and 13 and the reductions.
