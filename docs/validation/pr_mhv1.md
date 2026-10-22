# pr_mhv1 — Peng-Robinson MHV1 (NRTL)

family `mixing` · status **provisional** · adapter `ngdesign.thermo.mixing_rules:PRMHV1Thermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: Michelsen (1990) MHV1 mixing rule over thermo IPDB (ChemSep) 'ChemSep NRTL' binary matrices
- provenance: Michelsen, M. L., 'A modified Huron-Vidal mixing rule for cubic equations of state', Fluid Phase Equilib. 60, 213-219, 1990; NRTL binary parameters from the ChemSep IPDB via the T-03 gamma-phi adapter's loader (one owner of the parameter plumbing); k_ij-free form - the gE model carries all interaction information; zero-pressure gE reference (q1 = -0.53)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.3e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 3e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 4.3e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2398 dH/dT 42.2398 |
| gibbs_duhem | ok | 9.6e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 9.4e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 9.6e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: provisional on L0 only: the 4 bound pure cases miss on the untranslated PR liquid-density/Cp limits (declared above) and the 312.91 K binary case misses vapor_comp -3%; the two C1/H2O cases stay unbound (pending) because the NRTL databank has no C1/H2O pair and the row refuses, same as the pr_huron_vidal row. The 101.325 kPa binary bubble point PASSES - the zero-pressure reference is the right fix for the HV row's binary misses.

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

14/24 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pr-mhv1-pure-MeOH-305K` — coolprop:Methanol
- `pr-mhv1-pure-MeOH-330K` — coolprop:Methanol
- `pr-mhv1-pure-H2O-340K` — coolprop:Water
- `pr-mhv1-pure-H2O-370K` — coolprop:Water
- `pr-mhv1-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `pr-mhv1-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20

## References

- Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990
- Renon, H. & Prausnitz, J. M., AIChE J. 14(1), 135-144, 1968
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
