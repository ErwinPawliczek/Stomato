# Fluid catalytic cracker (`fcc`)

Family: **refining** · P&ID symbol: `FC`

Rigour ladder: R0 planned, R1 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | VGO feed |
| outlet | `dry_gas_out` | yes | dry gas |
| outlet | `lpg_out` | yes | LPG |
| outlet | `gasoline_out` | yes | gasoline |
| outlet | `lco_out` | yes | light cycle oil |
| outlet | `slurry_out` | yes | slurry/slops |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | yield correlation spec |
| R1 | planned | — | 5-lump kinetic model |
| R2 | planned | — | 10-lump kinetic model |

## References

- docs/unit-catalogue-plan.md §2 U-H 4

> roadmap.
