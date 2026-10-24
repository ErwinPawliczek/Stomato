# Control valve (`control_valve`)

Family: **flow** · P&ID symbol: `CV`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | throttled outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.control_valve:ControlValve` | Cv / outlet P spec, isenthalpic (the cv_liquid correlation plugin exists) |
| R1 | planned | — | IEC 60534 sizing, choked flow, Cv curve |

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V-control-valve-emerson-propane` | R0 | `info.Cv` | 113.2 | 113.419 | rel 0.005 | pass |
| `V-control-valve-emerson-propane` | R0 | `info.choked` | 0 | 0 | abs 0 | pass |

- `V-control-valve-emerson-propane`: Emerson control-valve sizing example, liquid propane: 800 gpm basis, SG 0.5, dP 25 psi, Fp 0.96, published Cv 117.9 (117.9 x 0.96 = 113.2 is the bare-valve Cv the adapter reports)

## References

- docs/unit-catalogue-plan.md §2 U-B 6

> R0 isenthalpic letdown; ISA liquid Cv is reported when the inlet is liquid and a viscosity is available (PR phase property or a mu_liquid param); IEC 60534 sizing and the choked-flow correlation remain roadmap.
