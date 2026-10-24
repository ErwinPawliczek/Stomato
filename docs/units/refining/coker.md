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
| R0 | provisional | `ngdesign.units.refining.reactors_coker:DelayedCoker` | Gary–Handwerk mass yields vs feed CCR (Table 5.5, p. 104); duty sensible-only (flag heat_of_reaction_basis_sensible_only) |

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
| `V1_coker_gh_case_study` | R0 | `info.coke_wt_pct` | 22.72 | 22.72 | rel 0.001 | pass |
| `V1_coker_gh_case_study` | R0 | `info.gas_wt_pct` | 9.84 | 9.8448 | rel 0.001 | pass |
| `V1_coker_gh_case_study` | R0 | `info.naphtha_wt_pct` | 16.16 | 16.1606 | rel 0.001 | pass |
| `V1_coker_gh_case_study` | R0 | `info.gasoil_wt_pct` | 51.3 | 51.2746 | rel 0.001 | pass |
| `V1_coker_gh_case_study` | R0 | `info.lgo_wt_pct` | 32.061 | 32.0603 | rel 0.001 | pass |
| `V1_coker_gh_case_study` | R0 | `info.hgo_wt_pct` | 19.214 | 19.2143 | rel 0.001 | pass |

- `V1_coker_gh_case_study`: Gary, Handwerk & Kaiser, Petroleum Refining: Technology and Economics, 5th ed. (2007), ch. 5, §5.9 case-study problem pp. 116-118 (printed product slate at coker-feed CCR 14.2 wt%)

## References

- docs/unit-catalogue-plan.md §2 U-H 11

> R0 shipped by U-H2 (Gary-Handwerk CCR yield equations, 5th ed. Table 5.5 p. 104; V1 is the book's own worked example - §5.9 case-study problem, pp. 116-118, printed product slate at coker-feed CCR 14.2 wt%; the Jechura CSM feed stays the example_case basis); products are mass-only pseudo lumps - the mass_elements element ledger has no atom sources for a pseudo feed (pseudo-component elemental characterization - issue #222). The refinery_leeps_distillation correlation plugin exists for LEEP cut yields.
