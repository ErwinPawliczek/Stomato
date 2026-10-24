# Delayed coker / visbreaker (`coker`)

Family: **refining** · P&ID symbol: `CK`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | residuum feed |
| outlet | `gas_out` | yes | coker gas |
| outlet | `naphtha_out` | yes | coker naphtha |
| outlet | `lgo_out` | yes | light gas oil |
| outlet | `hgo_out` | yes | heavy gas oil |
| outlet | `coke_out` | yes | petroleum coke |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.reactors_coker:DelayedCoker` | Gary–Handwerk mass yields vs feed CCR; duty sensible-only (flag heat_of_reaction_basis_sensible_only) |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa, default 4.0e5
    type: number
  T_out:
    description: outlet temperature, K, default 773.15
    type: number
  ccr_wt_pct:
    description: feed Conradson carbon residue, wt%
    type: number
  gasoil_lgo_fraction:
    description: LGO share of the gas-oil yield, in (0, 1), default 0.5
    type: number
required:
- ccr_wt_pct
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1_coker_jechura` | R0 | `info.coke_wt_pct` | 21.6 | 21.6 | abs 1e-06 | pass |
| `V1_coker_jechura` | R0 | `info.gas_wt_pct` | 9.744 | 9.744 | abs 1e-06 | pass |
| `V1_coker_jechura` | R0 | `info.naphtha_wt_pct` | 15.9205 | 15.9205 | abs 1e-06 | pass |
| `V1_coker_jechura` | R0 | `info.gasoil_wt_pct` | 52.7355 | 52.7355 | abs 1e-06 | pass |
| `V1_coker_jechura` | R0 | `info.lgo_wt_pct` | 26.3678 | 26.3678 | abs 1e-06 | pass |
| `V1_coker_jechura` | R0 | `info.hgo_wt_pct` | 26.3678 | 26.3678 | abs 1e-06 | pass |

- `V1_coker_jechura`: Gary, Handwerk & Kaiser, Petroleum Refining: Technology and Economics, 5th ed., ch. 5 CCR yield correlations, at the Jechura (CSM) example feed, 13.5 wt% CCR

## References

- docs/unit-catalogue-plan.md §2 U-H 11

> R0 shipped by U-H2 (Gary–Handwerk CCR table, Jechura CSM example basis); products are mass-only pseudo lumps — the mass_elements element ledger has no atom sources for a pseudo feed. The refinery_leeps_distillation correlation plugin exists for LEEP cut yields.
