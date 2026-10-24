# Naphtha hydrotreater (`naphtha_ht`)

Family: **refining** · P&ID symbol: `HT`

Rigour ladder: R0 provisional, R1 planned

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `naphtha_in` | yes | naphtha feed |
| inlet | `h2_in` | yes | hydrogen feed |
| outlet | `treated_out` | yes | hydrotreated naphtha |
| outlet | `gas_out` | yes | H2S / offgas |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.reactors_hdt:NaphthaHydrotreater` | Fahim E12.2 model-compound stoichiometry (thiophene HDS, pyridine HDN, olefin/aromatic saturation) with declared removal fractions; duty sensible-only |
| R1 | planned | — | lumped HDS/HDN kinetics in a PFR |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa, default 3.0e6
    type: number
  T_out:
    description: outlet temperature, K, default 620
    type: number
  benzene_conversion:
    description: aromatic saturation conversion, in [0, 1], default 0
    type: number
  nitrogen_removal_frac:
    description: feed nitrogen removal fraction, in [0, 1], default 1.0
    type: number
  pentene_conversion:
    description: olefin saturation conversion, in [0, 1], default 0
    type: number
  sulfur_removal_frac:
    description: feed sulfur removal fraction, in [0, 1], default 1.0
    type: number
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1_naphtha_ht_e12_2` | R0 | `info.h2s_mol_s` | 0.00749687 | 0.00748743 | rel 0.01 | pass |
| `V1_naphtha_ht_e12_2` | R0 | `info.nbutane_mol_s` | 0.00749687 | 0.00748743 | rel 0.01 | pass |
| `V1_naphtha_ht_e12_2` | R0 | `info.npentane_mol_s` | 0.0377994 | 0.0377277 | rel 0.01 | pass |
| `V1_naphtha_ht_e12_2` | R0 | `info.cyclohexane_mol_s` | 0.0193848 | 0.0193565 | rel 0.01 | pass |
| `V1_naphtha_ht_e12_2` | R0 | `info.h2_consumed_mol_s` | 0.124954 | 0.125747 | rel 0.01 | pass |

- `V1_naphtha_ht_e12_2`: Fahim, Al-Sahhaf & Elkilani, Fundamentals of Petroleum Refining, ch. 12, Example E12.2 (printed product slate)

## References

- docs/unit-catalogue-plan.md §2 U-H 7

> R0 shipped by U-H2. Sulfur rides on thiophene, nitrogen on pyridine; real H2/H2S/NH3 products from pseudo-lump feeds need pseudo-component elemental characterization (GitHub issue pending — see the PR).
