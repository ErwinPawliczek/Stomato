# Plate exchanger (`plate_exchanger`)

Family: **heat** · P&ID symbol: `PHE`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `hot_in` | yes | hot-side feed (liquid service) |
| inlet | `cold_in` | yes | cold-side feed |
| outlet | `hot_out` | yes | cooled hot outlet |
| outlet | `cold_out` | yes | warmed cold outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.heat.exchangers:PlateExchanger` | exactly one of duty_W / hot_T_out / cold_T_out; min-approach duty bisection, pinch check and LMTD/UA reported |
| R1 | planned | — | rating — chevron-correlation film coefficients |

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

## References

- docs/unit-catalogue-plan.md §2 U-C 4

> No V1 worked case: no single-exchanger printed example with complete printed inputs was located in accessible copies this round (the Kakaç & Liu duty example and the Perry Sect. 11 candidates were checked but not transcribed; Smith Table 16.1 is a network table, not one exchanger). The Smith Table 16.1 water-water streams are covered by the closed-form CP*ΔT test in tests/units/heat/test_exchangers.py; a V1 case needs a printed example with both feeds, an outlet spec and a printed duty/outlet.
