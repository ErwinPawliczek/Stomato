# Mixer (`mixer`)

Family: **logical** · P&ID symbol: `MIX`

Rigour ladder: R0 validated

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
| R0 | validated | `ngdesign.units.mixer:Mixer` | outlet pressure = min inlet pressure; adiabatic PH flash of the combined feed |

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-mixer-purdue-me200-steam-water` | R0 | `outlet.outlet.T` | 333.15 | 333.218 | abs 0.2 | pass |
| `V1-mixer-purdue-me200-steam-water` | R0 | `outlet.outlet.P` | 300000 | 300000 | abs 1 | pass |

- `V1-mixer-purdue-me200-steam-water`: Purdue University ME 200 Thermodynamics I lecture notes, Fall 2008, week 7 (https://engineering.purdue.edu/CFDLAB/class/me200/filesFall2008/me200_notes_f08_week7.pdf), p. 7 "Mixing chambers" example, read 2026-11-04 (the Cengel & Boles mixing-chamber example): liquid water at 300 kPa and 20 C (1.8 kg/s) is heated in an adiabatic chamber by superheated steam at 300 kPa and 300 C; the mixture leaves at 60 C; printed h1 = 83.96, h2 = 3069.3, h3 = 251.13 kJ/kg (compressed liquid taken as saturated liquid), answer m2 = 0.107 kg/s. The case runs the solved flows forward (1.8 kg/s = 99.915 mol/s, 0.107 kg/s = 5.9394 mol/s at M = 18.015268 g/mol) and checks the mixed outlet against the printed 60 C. Tolerance: the 3-decimal print of m2 (+/-0.0005 kg/s) moves the mixed temperature by +/-0.18 K (0.0005 x (3069.3 - 251.13) kJ/s over 1.907 kg/s x 4.18 kJ/kg K), rounded up to 0.2 K before the run.

## References

- docs/unit-catalogue-plan.md §2 U-A 1

> complete at R0 (plan §1) — a mixer has no rating or rigorous level.
