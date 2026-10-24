# Ejector (`ejector`)

Family: **flow** · P&ID symbol: `EJ`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `motive_in` | yes | motive stream |
| inlet | `suction_in` | yes | suction stream |
| outlet | `outlet` | yes | combined discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.ejector:Ejector` | entrainment ratio spec |
| R1 | planned | — | 1-D momentum (ESDU-style) |

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V-ejector-graham-3to1` | R0 | `info.motive_to_suction_required` | 3 | 3 | rel 1e-06 | pass |
| `V-ejector-graham-3to1` | R0 | `info.entrainment_achieved` | 0.333333 | 0.333336 | rel 0.001 | pass |

- `V-ejector-graham-3to1`: Graham Manufacturing ejector performance data: 3:1 motive/suction mass-ratio operating point (steam both streams, 146.873 mol/s motive at 6.0e5 Pa / 433.15 K entraining 48.958 mol/s at 5.0e4 Pa to 1.0e5 Pa discharge)

## References

- docs/unit-catalogue-plan.md §2 U-B 10

> R0 momentum balance at a specified entrainment ratio; 1-D momentum design mode remains roadmap.
