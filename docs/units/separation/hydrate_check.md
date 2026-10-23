# Hydrate check / inhibitor injection (`hydrate_check`)

Family: **separation** · P&ID symbol: `HC`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | gas stream at risk of hydrates |
| inlet | `inhibitor_in` | no | inhibitor (MeOH/MEG) injection |
| outlet | `outlet` | yes | gas with hydrate margin and inhibitor dose reported |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | hydrate T from Hammerschmidt + inhibitor dose (the hammerschmidt_formation correlation plugin exists) |
| R1 | planned | — | Katz / van der Waals-Platteeuw (via thermo) |

## References

- docs/unit-catalogue-plan.md §2 U-D 10

> roadmap; S2 slice (plan §2b).
