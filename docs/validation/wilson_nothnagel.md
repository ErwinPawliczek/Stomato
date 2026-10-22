# wilson_nothnagel — Wilson liquid + Nothnagel virial vapour — Tsonopoulos (fallback)

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: Nothnagel (1973) b/K parameter table not available from open sources; the row builds the declared Tsonopoulos-extended second-virial fallback (ngdesign.thermo.virial) (spec deviation)
- provenance: real second-virial phase via the declared Tsonopoulos-extended fallback; the row name identifies that Nothnagel parameters remain unavailable (spec deviation)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 2.8e-16 | 380K/50000Pa T_ph 0 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 0 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 42.9104 dH/dT 42.9104 |
| gibbs_duhem | ok | 1e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 2.6e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep Wilson databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

29/31 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-323.5K-nothnagel` — coolprop:Water
- `pure-H2O-420K-nothnagel` — coolprop:Water
- `pure-nC4-350K-nothnagel` — coolprop:n-Butane
- `meohh2o-101.325kPa-366.0K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-361.35K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-356.95K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-353.25K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-349.05K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-346.20K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-343.31K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-341.20K-nothnagel` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22

## References

- Nothnagel, K.-H., Abrams, D. S. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 12(1), 25-35, 1973 (b/K parameter table not available from open sources)
- Tsonopoulos, C., AIChE J. 20(2), 263-272, 1974 (extended correlation used by the declared fallback)
