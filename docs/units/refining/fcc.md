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

> roadmap; nothing above R1 is planned (plan §2 U-H preamble). R0 record of what was searched (U-H2 review) - the published FCC yield correlations are chart/figure-based (Gary, Handwerk & Kaiser, Petroleum Refining, 5th ed. 2007, §6.12 Yield Estimation, pp. 143-144, points at Figures 6.17-6.28) and the U-R1 conventions forbid digitising figures; no equation-based R0 correlation was found in the open sources searched, so the row stays planned rather than shipping a figure-transcription.
