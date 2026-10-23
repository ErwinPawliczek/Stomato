# Mixer (`mixer`)

Family: **logical** · P&ID symbol: `MIX`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet_1` | yes | first feed |
| inlet | `inlet_2` | yes | second feed |
| inlet | `inlet_3` | yes | third feed |
| outlet | `outlet` | yes | adiabatic mixed stream |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.mixer:Mixer` | outlet pressure = min inlet pressure; adiabatic PH flash of the combined feed |

## References

- docs/unit-catalogue-plan.md §2 U-A 1

> complete at R0 (plan §1) — a mixer has no rating or rigorous level.
