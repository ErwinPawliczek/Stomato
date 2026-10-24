# Double-pipe / hairpin exchanger (`double_pipe`)

Family: **heat** · P&ID symbol: `E`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `hot_in` | yes | hot-side feed (gas service) |
| inlet | `cold_in` | yes | cold-side feed |
| outlet | `hot_out` | yes | cooled hot outlet |
| outlet | `cold_out` | yes | warmed cold outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.exchangers:DoublePipeExchanger` | exactly one of duty_W / hot_T_out / cold_T_out; min-approach duty bisection, pinch check and LMTD/UA reported |
| R1 | planned | — | rating |

### R0 parameters

```yaml
properties:
  cold_T_out:
    description: cold outlet temperature spec, K
    type: number
  dP_cold:
    description: cold-side pressure drop, Pa
    type: number
  dP_hot:
    description: hot-side pressure drop, Pa
    type: number
  duty_W:
    description: duty spec, W (one of duty_W/hot_T_out/cold_T_out)
    type: number
  hot_T_out:
    description: hot outlet temperature spec, K
    type: number
  min_approach_K:
    description: solve the duty for this minimum approach, K
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V2082` | R0 | `outlet.cold_out.T` | 322.039 | 322.977 | abs 0.28 | assessed miss |
| `V2082` | R0 | `info.duty_W` | 48943 | 44974.3 | rel 0.02 | assessed miss |

- `V2082`: Kern, Process Heat Transfer, Example 6.1: 9,820 lb/h of benzene heated 80 -> 120 F against 6,330 lb/h of toluene cooled 160 -> 100 F, Q = 6,330 * 0.44 * 60 = 167,000 Btu/h = 48,943 W. Flows from the printed lb/h over the package molar masses: toluene 8.66 mol/s, benzene 15.84 mol/s.
  - assessed: Measured: benzene outlet 322.969 K (+0.93 K over the book's 120 F) and duty 44,968 W (-8.1% on the printed 167,000 Btu/h). Kern's chart cp values (toluene 0.44, benzene 0.47 Btu/lb-F) sit a few percent above the PR package's liquid cp at these conditions, and the printed-input arithmetic carries that gap end to end; the exchanger itself closes exactly (hot outlet at the spec'd 100 F). Documented as a property-package difference rather than hidden by a loosened tolerance.

## References

- docs/unit-catalogue-plan.md §2 U-C 5

> V2082 runs Kern Example 6.1's printed inputs (9,820 lb/h benzene, 6,330 lb/h toluene, 160 -> 100 F); measured duty 44,968 W (-8.1%) and benzene outlet +0.93 K are assessed against the book's chart cp values, not widened away.
