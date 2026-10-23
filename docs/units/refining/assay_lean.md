# Assay-based feed characterization (`assay_lean`)

Family: **refining** · P&ID symbol: `ASSAY`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `assay_in` | yes | crude assay data |
| outlet | `cuts_out` | yes | TBP cuts / pseudo-component slate |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | TBP to cuts with shift factors (Riazi-Daubert); the riazi_daubert correlation plugin exists |

## References

- docs/unit-catalogue-plan.md §2 U-H 10

> roadmap; pairs with the A-01 assay work (issue
