# Hydrocracker (`hcu`)

Family: **refining** · P&ID symbol: `HC`

Rigour ladder: R0 planned, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `vgo_in` | yes | VGO feed |
| inlet | `hydrogen_in` | yes | hydrogen feed |
| outlet | `naphtha_out` | yes | hydrocracked naphtha |
| outlet | `diesel_out` | yes | diesel |
| outlet | `unconverted_out` | yes | unconverted oil recycle |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | yield table vs conversion |
| R1 | planned | — | lumped (continuous-lumping) kinetics |

## References

- docs/unit-catalogue-plan.md §2 U-H 10

> roadmap. R0 record of what was searched (U-H2 review) - published hydrocracker yield correlations are chart/figure-based (Gary, Handwerk & Kaiser, Petroleum Refining, 5th ed. 2007, §7.6 Hydrocracking Yields, pp. 170-172, reads Figure 7.4 / Figure 7.6 curves; its Table 7.3 is fixed-feed vol% tables, not a correlation) and the U-R1 conventions forbid digitising figures, so the row stays planned rather than shipping a figure-transcription.
