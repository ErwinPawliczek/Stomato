# lcvm — LCVM (PR + linear Vidal/MHV1 combination over original UNIFAC)

family `mixing` · status **provisional** · adapter `ngdesign.thermo.mixing_rules:PRLCVMThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: LCVM (Boukouvalas et al. 1994): PR with the linear Vidal/MHV1 combination (lambda = 0.36, the original Boukouvalas weighting) over original UNIFAC (thermo unifac variant)
- provenance: Boukouvalas, C. J., Spiliotis, N., Coutsikos, P., Tzoupanekos, N. & Magoulas, K., "Prediction of vapor-liquid equilibria with the LCVM model", Fluid Phase Equilib. 92, 75-89, 1994; Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990 (MHV1 reference, q1 = -0.62363 for PR); k_ij-free form - the gE model carries all interaction information

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 3e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 3e-16; 400K/100000Pa T_ph 2.8e-16 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2409 dH/dT 42.2409 |
| gibbs_duhem | ok | 1.2e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.2e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 4.6e-10 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: provisional on L0 only: the 6 bound T-12 cases (4 L1 pure, 2 L2 MeOH/H2O VLE) all miss (declared above; the two C1/H2O cases stay unbound because the original-UNIFAC curated map has no C1 assignment and the row refuses) - the pure points inherit the untranslated PR limits and the MeOH/H2O points show the 64/36 Vidal/Michelsen weighting with original-UNIFAC parameters over-predicts alcohol-water bubble temperatures; promotion needs LCVM-assessed gE evidence beyond the transferred UNIFAC basis

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

11/24 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `lcvm-pure-MeOH-305K` — coolprop:Methanol
- `lcvm-pure-MeOH-330K` — coolprop:Methanol
- `lcvm-pure-H2O-340K` — coolprop:Water
- `lcvm-pure-H2O-370K` — coolprop:Water
- `lcvm-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `lcvm-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20

## References

- Boukouvalas, C. J., Spiliotis, N., Coutsikos, P., Tzoupanekos, N. & Magoulas, K., Fluid Phase Equilib. 92, 75-89, 1994
- Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990
