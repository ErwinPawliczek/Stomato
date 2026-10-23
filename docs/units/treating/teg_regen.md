# TEG regenerator + stripping gas (`teg_regen`)

Family: **treating** · P&ID symbol: `T`

Rigour ladder: R0 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `rich_in` | yes | rich glycol |
| inlet | `stripping_gas_in` | no | stripping gas |
| outlet | `water_out` | yes | stripped water |
| outlet | `lean_out` | yes | regenerated glycol |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | shortcut water split at spec purity |
| R2 | planned | — | staged — S1 slice (plan §2b) |

## References

- docs/unit-catalogue-plan.md §2 U-G 4

> roadmap.
