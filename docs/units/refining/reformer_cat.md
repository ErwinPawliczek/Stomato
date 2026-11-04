# Catalytic reformer (`reformer_cat`)

Family: **refining** · P&ID symbol: `RF`

Rigour ladder: R0 validated, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `naphtha_in` | yes | naphtha feed |
| outlet | `reformate_out` | yes | reformate |
| outlet | `h2_out` | yes | hydrogen by-product |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | validated | `ngdesign.units.refining.reactors_reformer:CatalyticReformer` | Fahim Table 5.3 lumped yields vs reformate RON; duty sensible-only (flag heat_of_reaction_basis_sensible_only) |
| R1 | provisional | `ngdesign.units.refining.reformer_kinetic:CatalyticReformerR1` | Smith (1959) four-reaction scheme on representative C7 species in adiabatic beds with interheaters, on the pfr integrator; the constants are required inputs |

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

### R1 parameters

```yaml
properties:
  beds:
    description: '[{catalyst_mass_kg, inlet_T_K (interheater set point), thermal:
      adiabatic|isothermal}] in flow order'
    type: array
  bulk_density_kg_m3:
    description: catalyst bulk density, kg/m3
    type: number
  kinetics:
    description: 'required explicit {dehydro|n_to_p: {k0, Ea, A_K, B_K}, hc_n|hc_p:
      {k0, Ea}}; k0 in mol/(kg_cat s atm^order), Ea J/mol, K = exp(A_K - B_K/T[K]);
      the smith1959 preset is refused'
required:
- beds
- bulk_density_kg_m3
- kinetics
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

> R1 takes Smith's constants as a required explicit input and refuses the smith1959 preset - Smith 1959 could not be read, and the open reproduction (Liang, Guo and Pan, J. Zhejiang Univ. Sci. B 6(6) 2005 590-596, eqs. 9-17) prints k_p2 with a 9.87 prefactor against MPa-2 units that need 97.4. V1 gap - that paper omits catalyst masses, so its plant table cannot be reproduced; provisional on the hand equilibrium of dehydro and the unit conversions. No R1 limit reproduces R0 (a different model). R0 shipped by U-H2. The spec's "H2 and light ends as real components" is out of reach of the mass_elements balance (C/H atoms with no formula-bearing source from a pseudo naphtha); the offgas is a mass-only lump, species split in info. Pseudo-component elemental characterization - issue #222.
