# Catalytic reformer (`reformer_cat`)

Family: **refining** · P&ID symbol: `RF`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `naphtha_in` | yes | naphtha feed |
| outlet | `reformate_out` | yes | reformate |
| outlet | `h2_out` | yes | hydrogen by-product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.reactors_reformer:CatalyticReformer` | Fahim Table 5.3 lumped yields vs reformate RON; duty sensible-only (flag heat_of_reaction_basis_sensible_only) |
| R1 | planned | — | Smith (1959) lumped kinetics |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa, default 3.0e6
    type: number
  T_out:
    description: outlet temperature, K, default 780
    type: number
  aromatics_vol_pct:
    description: feed aromatics, vol%
    type: number
  naphthenes_vol_pct:
    description: feed naphthenes, vol%
    type: number
  ron_reformate:
    description: target reformate RON (correlation fitted near 80-104)
    type: number
required:
- ron_reformate
- naphthenes_vol_pct
- aromatics_vol_pct
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1_reformer_e5_2` | R0 | `info.c5p_vol_pct` | 80.17 | 80.1751 | rel 0.001 | pass |
| `V1_reformer_e5_2` | R0 | `info.h2_wt_pct` | 2.1051 | 2.10515 | rel 0.005 | pass |
| `V1_reformer_e5_2` | R0 | `info.c1_wt_pct` | 1.4871 | 1.48711 | rel 0.005 | pass |
| `V1_reformer_e5_2` | R0 | `info.c2_wt_pct` | 2.4012 | 2.40121 | rel 0.005 | pass |
| `V1_reformer_e5_2` | R0 | `info.c3_wt_pct` | 3.6441 | 3.64408 | rel 0.005 | pass |
| `V1_reformer_e5_2` | R0 | `info.c4_total_wt_pct` | 4.2784 | 4.27831 | rel 0.005 | pass |

- `V1_reformer_e5_2`: Fahim, Al-Sahhaf & Elkilani, Fundamentals of Petroleum Refining, ch. 5, worked Example E5.2 (printed product slate)

## References

- docs/unit-catalogue-plan.md §2 U-H 8

> R0 shipped by U-H2. The spec's "H2 and light ends as real components" is out of reach of the mass_elements balance (C/H atoms with no formula-bearing source from a pseudo naphtha); the offgas is a mass-only lump, species split in info. GitHub issue on pseudo-component elemental characterization pending.
