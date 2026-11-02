# Control valve (`control_valve`)

Family: **flow** · P&ID symbol: `CV`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | throttled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.control_valve:ControlValve` | Cv / outlet P spec, isenthalpic (the cv_liquid correlation plugin exists) |
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
| `V-control-valve-emerson-propane` | R0 | `info.Cv` | 113.2 | 113.419 | rel 0.005 | pass |
| `V-control-valve-emerson-propane` | R0 | `info.choked` | 0 | 0 | abs 0 | pass |

- `V-control-valve-emerson-propane`: Emerson control-valve sizing example, liquid propane: 800 gpm basis, SG 0.5, dP 25 psi, Fp 0.96, published Cv 117.9 (117.9 x 0.96 = 113.2 is the bare-valve Cv the adapter reports)

## References

- docs/unit-catalogue-plan.md §2 U-B 6

> R0 isenthalpic letdown; ISA liquid Cv is reported when the inlet is liquid and a viscosity is available (PR phase property or a mu_liquid param); IEC 60534 sizing and choked flow are R1. R1 V1 gap - the IEC 60534-2-1 Annex D printed Kv values could not be read from an open copy and the fluids docstring numbers are model output, not valid V1; provisional on the spec hand calculations of eqs. 1-4, 8, 10 and 13 and the reductions.
