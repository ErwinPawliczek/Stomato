# pr_huron_vidal — Peng-Robinson Huron-Vidal (NRTL)

family `mixing` · status **provisional** · adapter `ngdesign.thermo.mixing_rules:PRHuronVidalThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: Huron-Vidal (1979) mixing rule over thermo IPDB (ChemSep) 'ChemSep NRTL' binary matrices
- provenance: Huron, M.-J. & Vidal, J., 'New mixing rules in simple equations of state for representing vapour-liquid equilibria of strongly non-ideal mixtures', Fluid Phase Equilib. 3, 255-271, 1979; NRTL binary parameters from the ChemSep IPDB via the T-03 gamma-phi adapter's loader (one owner of the parameter plumbing); k_ij-free form - the gE model carries all interaction information

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 3e-16 | 380K/50000Pa T_ph 3e-16 H 0 T_ps 0; 400K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2417 dH/dT 42.2417 |
| gibbs_duhem | ok | 1.1e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.1e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 1.3e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: provisional on L0 only: the 6 bound T-12 cases all miss (declared above; the two C1/H2O cases stay unbound because the NRTL databank has no C1/H2O pair and the row refuses) - the pure points inherit the untranslated PR liquid-density/Cp limits and the MeOH/H2O points show that the ChemSep NRTL parameters (low-pressure gamma-phi fits) do not transfer to the Huron-Vidal infinite-pressure reference; promotion needs an HV-specific NRTL parameter set with a citation (Huron & Vidal 1979 Table 2 or a later open fit) bound as an independent case

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

11/24 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pr-huron-vidal-pure-MeOH-305K` — coolprop:Methanol
- `pr-huron-vidal-pure-MeOH-330K` — coolprop:Methanol
- `pr-huron-vidal-pure-H2O-340K` — coolprop:Water
- `pr-huron-vidal-pure-H2O-370K` — coolprop:Water
- `pr-huron-vidal-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `pr-huron-vidal-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20

## References

- Huron, M.-J. & Vidal, J., Fluid Phase Equilib. 3, 255-271, 1979
- Renon, H. & Prausnitz, J. M., AIChE J. 14(1), 135-144, 1968
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
