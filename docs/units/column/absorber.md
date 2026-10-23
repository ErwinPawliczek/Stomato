# Absorber (feed-determined) (`absorber`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 planned, R2 planned, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | feed gas |
| inlet | `solvent_in` | yes | lean solvent |
| outlet | `gas_out` | yes | treated gas |
| outlet | `rich_out` | yes | rich solvent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | Kremser stage count (the kremser correlation plugin exists in sizing) |
| R2 | planned | — | MESH zero-tear — today via the `column` row's absorber configuration |
| R3 | planned | — | rate-based stages |

## References

- docs/unit-catalogue-plan.md §2 U-E 3

> the amine-specific rows live in the treating family; this row is the generic solvent absorber.
