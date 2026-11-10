# srk_wong_sandler — Soave-Redlich-Kwong Wong-Sandler (NRTL)

family `mixing` · status **provisional** · adapter `ngdesign.thermo.mixing_rules:SRKWongSandlerThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: Wong-Sandler (1992) mixing rule over thermo IPDB (ChemSep) 'ChemSep NRTL' binary matrices
- provenance: Wong, D. S. H. & Sandler, S. I., 'A theoretically correct mixing rule for cubic equations of state for vapor-liquid equilibria', AIChE J. 38(5), 671-680, 1992; NRTL binary parameters from the ChemSep IPDB via the T-03 gamma-phi adapter's loader (one owner of the parameter plumbing); k_ij-free form - the gE model carries all interaction information; the rule's C constant is the SRK form -ln(2)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.2e-16 | 380K/50000Pa T_ph 1.5e-16 H 4.2e-16 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 3.4e-16 T_ps 2.8e-16 |
| dhdT_cp | ok | 5.2e-06 | 380K/50000Pa vapor cp 42.246 dH/dT 42.2458 |
| gibbs_duhem | ok | 2.3e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 9e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 2.3e-08 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: provisional: on the Gao 2012 isobar the row passes only 341.20 K (bubble T +3..+3.7 K water-rich): Wong-Sandler without a fitted k_ij. Promotion needs a WS-fitted k_ij / gE set with a citation. Evidence (re-measured 2026-11-04): L1 = the shared CoolProp pure-hydrocarbon points (mix-pure-*; the rule collapses to its host cubic on a pure feed, so the polar MeOH/H2O pure points carry the host's untranslated liquid-density/Cp misses, assessed above); L2 = the full Gao et al. 2012 MeOH/H2O 101.325 kPa isobar (mix-meohh2o-*, 8 points). The Bayer 1927 312.91 K point is also missed by the validated nrtl row (data quality).

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

28/48 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `srk-wong-sandler-pure-MeOH-305K` — coolprop:Methanol
- `srk-wong-sandler-pure-MeOH-330K` — coolprop:Methanol
- `srk-wong-sandler-pure-H2O-340K` — coolprop:Water
- `srk-wong-sandler-pure-H2O-370K` — coolprop:Water
- `srk-wong-sandler-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `mix-pure-nC4-280K` — coolprop:n-Butane
- `mix-pure-C3-240K` — coolprop:Propane
- `mix-meohh2o-101.325kPa-366.0K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-361.35K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-356.95K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-353.25K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-346.20K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-343.31K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-341.20K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22

## References

- Wong, D. S. H. & Sandler, S. I., AIChE J. 38(5), 671-680, 1992
- Soave, G., Chem. Eng. Sci. 27(6), 1197-1203, 1972
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
