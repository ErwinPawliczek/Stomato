# Catalytic reformer (`reformer_cat`)

Family: **refining** · P&ID symbol: `RF`

Rigour ladder: R0 provisional, R1 provisional

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
| R1 | provisional | `ngdesign.units.refining.reformer_kinetic:CatalyticReformerR1` | Smith (1959) four-reaction lumped kinetics (n = 7: dehydro N<=>A+3H2, n_to_p N+H2<=>P, hc_n and hc_p hydrocracking to equal-molar C1-C5) over real C7 lumps (P = nC7, N = methylcyclohexane, A = toluene); adiabatic beds with fired interheaters on the pfr R1 integrator, isobaric per bed (no dP at R1), exact thermal_outlet closures, sharp reformate/H2 split; feed restricted to the real-species slate (issue #222) |

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
    description: 'per bed, in flow order: {catalyst_mass_kg (> 0), inlet_T_K (> 0,
      the fired interheater set point), thermal: "adiabatic" (default) | "isothermal"}'
    type: array
  bulk_density_kg_m3:
    description: catalyst bulk density, kg/m3 (> 0); converts the per-catalyst-mass
      rates (bed volume V_b = W_b / rho_b)
    type: number
  kinetics:
    description: "{dehydro|n_to_p: {k0, Ea, A_K, B_K}, hc_n|hc_p: {k0, Ea}} Smith-form\
      \ constants \u2014 k0 in lb-mol/(h\xB7lb_cat\xB7atm^\u03A3orders) (eq. 4 folds\
      \ C_u and the bed P_atm into the contract k0'), Ea in J/mol, K = exp(A_K - B_K/T[K]);\
      \ the \"smith1959\" preset is refused until Smith's constants are transcribed\
      \ with page numbers"
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

> R0 shipped by U-H2. The spec's "H2 and light ends as real components" is out of reach of the mass_elements balance (C/H atoms with no formula-bearing source from a pseudo naphtha); the offgas is a mass-only lump, species split in info. Pseudo-component elemental characterization - issue #222. R1 implemented (U-R2 wave): Smith (1959) four-reaction kinetics over real C7 lumps (P = nC7, N = methylcyclohexane, A = toluene), adiabatic beds with interheaters on the pfr R1 integrator, sharp reformate/H2 split; the row has no identity with R0 (kinetics vs a yield correlation), so the R1 identity is all k0 = 0 (tests/units/refining/test_reformer_cat_r1.py). V1 gap (2026-10-26): Smith (1959) CEP 55(6) 76-80 is not openly accessible and Rase (Chemical Reactor Design for Process Plants, vol. 2, 1977) catalytic-reforming case study has no open copy (searched Open Library, Google Books, publisher pages); open secondary reproductions of the Smith model exist (a TSI-journals reactor-modeling paper, the Lid & Skogestad NTNU preprint) but printing a page-cited transcription of Smith's k_i/K_i tables was not completed in the time box, so the smith1959 preset stays refused and the level ships provisional on its closed-form tests (dehydro equilibrium at 1e-6 rel, _smith_to_contract conversion checks, k0 = 0 identity, three-bed adiabatic V0 at 1e-8).
