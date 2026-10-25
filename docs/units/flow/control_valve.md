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
| R1 | provisional | `ngdesign.units.flow.control_valve_r1:ControlValveR1` | IEC 60534-2-1 sizing/rating, choked flow, inherent characteristic. V1 (liquid): expected Kv transcribed from the printed results of ISA-75.01.01-2007 (IEC 60534-2-1 Mod) Annex E Examples 1 and 2 — C = Kv = 165 and 238 m3/h, three significant figures, which the 0.5 percent tolerance reflects. V1 gap (gas, Annex D/E Example 3, CO2 433 K): the printed no-fittings value 62.7 m3/h is an intermediate first pass with FP = 1 assumed, and the final printed 72.1 m3/h embeds the FP/xTP fittings iteration, while the adapter takes MW/Z/gamma/viscosity from the thermo and cannot be pinned to the printed state (nu 1.743e-5 m2/s, Z 0.988); search places were IEC 60534-2-1:2011 Annex D, the ISA-75.01.01-2007 Annex, and the Emerson Control Valve Handbook 5th ed. ch. 5. |

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
| `V1-control-valve-iec60534-annexD-ex1-liquid` | R1 | `info.Kv_m3h_bar05` | 165 | 164.996 | rel 0.005 | pass |
| `V1-control-valve-iec60534-annexD-ex1-liquid` | R1 | `info.choked` | 0 | 0 | abs 0 | pass |
| `V1-control-valve-iec60534-annexD-ex2-liquid-choked` | R1 | `info.Kv_m3h_bar05` | 238 | 238.073 | rel 0.005 | pass |
| `V1-control-valve-iec60534-annexD-ex2-liquid-choked` | R1 | `info.choked` | 1 | 1 | abs 0 | pass |

- `V-control-valve-emerson-propane`: Emerson control-valve sizing example, liquid propane: 800 gpm basis, SG 0.5, dP 25 psi, Fp 0.96, published Cv 117.9 (117.9 x 0.96 = 113.2 is the bare-valve Cv the adapter reports)
- `V1-control-valve-iec60534-annexD-ex1-liquid`: ISA-75.01.01-2007 (IEC 60534-2-1 Mod) Annex E Example 1 (water, globe valve, non-choked, no fittings), printed inputs: rho1 965.4 kg/m3, P1 680 kPa, P2 220 kPa, Q 360 m3/h, T1 363 K, Pv 70.1 kPa, Pc 22120 kPa, nu 3.26e-7 m2/s (mu 3.1472e-4 Pa s), FL 0.9. Printed result: C = Kv = 165 m3/h.
- `V1-control-valve-iec60534-annexD-ex2-liquid-choked`: ISA-75.01.01-2007 (IEC 60534-2-1 Mod) Annex E Example 2 (water, ball valve, choked, no fittings), same printed inputs with FL 0.6: rho1 965.4 kg/m3, P1 680 kPa, P2 220 kPa, Q 360 m3/h, T1 363 K, Pv 70.1 kPa, Pc 22120 kPa, nu 3.26e-7 m2/s. Printed result: C = Kv = 238 m3/h (eq. 3).

## References

- docs/unit-catalogue-plan.md §2 U-B 6

> R0 isenthalpic letdown; ISA liquid Cv is reported when the inlet is liquid and a viscosity is available (PR phase property or a mu_liquid param). R1 adds IEC 60534-2-1 sizing and rating with choked flow, piping-geometry factors and inherent characteristics.
