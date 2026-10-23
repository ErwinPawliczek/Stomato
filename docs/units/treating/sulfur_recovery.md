# Claus sulfur recovery (`sulfur_recovery`)

Family: **treating** · P&ID symbol: `SRU`

Rigour ladder: R0 planned, R2 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `acid_gas_in` | yes | acid gas feed |
| outlet | `tail_gas_out` | yes | tail gas |
| outlet | `sulfur_out` | yes | liquid sulfur |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | conversion/equilibrium per stage |
| R2 | planned | — | Gibbs per stage |

## References

- docs/unit-catalogue-plan.md §2 U-G 5

> roadmap; S2 slice (plan §2b). Sour-water stripping is NOT a row here — it is a reboiled-stripper configuration on the electrolyte package (T-09, plan U-G 9).
