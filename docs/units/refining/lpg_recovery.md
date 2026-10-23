# LPG recovery (lean-oil absorption) (`lpg_recovery`)

Family: **refining** · P&ID symbol: `NGL`

Rigour ladder: R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `gas_in` | yes | feed gas |
| inlet | `lean_oil_in` | yes | absorption oil |
| outlet | `lean_gas_out` | yes | lean gas |
| outlet | `rich_oil_out` | yes | rich oil |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | planned | — | a flowsheet built from the column-family absorber + regenerator rows, not a bespoke unit (plan §2 decision — LNG/NGL templates are excluded as flowsheet templates) |

## References

- docs/unit-catalogue-plan.md §2 U-H 11

> roadmap; recorded here as documentation of the template decision — no dedicated adapter is planned. LNG liquefaction likewise ships as an example flowsheet (plan §2 U-H 12).
