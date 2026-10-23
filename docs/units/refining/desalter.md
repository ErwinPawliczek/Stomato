# Desalter (`desalter`)

Family: **refining** · P&ID symbol: `DS`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `crude_in` | yes | crude feed |
| inlet | `wash_in` | yes | wash water |
| outlet | `crude_out` | yes | desalted crude |
| outlet | `water_out` | yes | salty waste water |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | water/salt/BS&W split spec, wash-water mix |
| R1 | planned | — | efficiency vs wash rate and ΔT (cited correlation) |

## References

- docs/unit-catalogue-plan.md §2 U-H 2

> roadmap.
