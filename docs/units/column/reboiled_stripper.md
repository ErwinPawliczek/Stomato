# Reboiled stripper (`reboiled_stripper`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R0 planned, R2 planned, R3 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | liquid feed to the top stage |
| outlet | `overhead` | yes | stripped overhead |
| outlet | `bottoms` | yes | lean bottoms |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | Kremser on the stripping side |
| R2 | planned | — | MESH one-tear (kettle only) — today via the `column` row's stripper configuration |
| R3 | planned | — | rate-based stages |

## References

- docs/unit-catalogue-plan.md §2 U-E 4

> sour-water stripping (plan U-G 9) is a reboiled-stripper configuration on an electrolyte package (T-09) — no separate treating row.
