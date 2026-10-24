# Orifice / flow element (`orifice`)

Family: **flow** · P&ID symbol: `FE`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | element inlet |
| outlet | `outlet` | yes | element outlet |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.orifice:Orifice` | ΔP from a discharge coefficient |
| R1 | planned | — | ISO 5167 sizing |

## References

- docs/unit-catalogue-plan.md §2 U-B 9

> R0 fixed-Cd dP read; ISO 5167 sizing remains roadmap.
