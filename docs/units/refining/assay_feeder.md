# Assay feeder (`assay_feeder`)

Family: **refining** · P&ID symbol: `ASSAY`

Rigour ladder: R0 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `assay_in` | yes | crude assay data (A-01 data layer) |
| outlet | `cuts_out` | yes | pseudo-component stream at T, P, flow |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | planned | — | assay (A-01) → pseudo-component stream at T, P, flow |

## References

- docs/unit-catalogue-plan.md §2 U-H 1

> roadmap; pairs with the A-01 assay work and the flowsheet-owned pseudo-components (P1-14); assay cutting is data-layer work.
