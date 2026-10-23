# Fluid catalytic cracker (`fcc`)

Family: **refining** · P&ID symbol: `FC`

Rigour ladder: R0 planned, R1 planned

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
| R0 | planned | — | yield table vs conversion |
| R1 | planned | — | Weekman 3/4-lump kinetics with heat balance |

## References

- docs/unit-catalogue-plan.md §2 U-H 9

> roadmap; nothing above R1 is planned (plan §2 U-H preamble).
