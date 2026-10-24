# Relief valve (`relief_valve`)

Family: **flow** · P&ID symbol: `PSV`

Rigour ladder: R0 provisional, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | relieved stream at set pressure |
| outlet | `outlet` | yes | discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.relief_valve:ReliefValve` | set pressure, orifice from API 520 (the psv_api520_gas correlation plugin exists) |
| R1 | planned | — | two-phase sizing (HEM/omega) |
| R2 | planned | — | inlet/outlet loss checks |

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V-relief-valve-api520-ex1` | R0 | `info.required_area_in2` | 6.51 | 6.49546 | rel 0.005 | pass |
| `V-relief-valve-api520-ex1` | R0 | `info.selected_orifice_area_in2` | 11.05 | 11.05 | rel 1e-09 | pass |

- `V-relief-valve-api520-ex1`: API 520 Part I, 10th ed., sec. 5.6.3.2 Example 1: required orifice area 6.51 in2 (adapter reproduces the API 526 letter selection, not the rounded print)

## References

- docs/unit-catalogue-plan.md §2 U-B 7

> R0 gas PSV sizing per API 520 Part I with API 526 orifice selection; two-phase sizing and relief-system loss checks remain roadmap.
