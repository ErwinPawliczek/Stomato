# lcvm — LCVM (PR + linear Vidal/MHV1 combination over original UNIFAC)

family `mixing` · status **validated** · adapter `ngdesign.thermo.mixing_rules:PRLCVMThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: LCVM (Boukouvalas et al. 1994): PR with the linear Vidal/MHV1 combination (lambda = 0.36 on the Vidal term, A_V = -0.623, A_M = -0.52) over original UNIFAC (thermo unifac variant)
- provenance: Boukouvalas, C., Spiliotis, N., Coutsikos, P., Tzouvaras, N. & Tassios, D., "Prediction of vapor-liquid equilibrium with the LCVM model", Fluid Phase Equilib. 92, 75-106, 1994 (alpha = A + (lambda/A_V + (1-lambda)/A_M) gE/RT + ((1-lambda)/A_M) sum x ln(b/b_i), lambda = 0.36, A_V = -0.623, A_M = -0.52 for PR); Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990 (MHV1 reference); k_ij-free form - the gE model carries all interaction information

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 7e-16 | 380K/50000Pa T_ph 3e-16 H 7e-16 T_ps 1.5e-16; 400K/100000Pa T_ph 0 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2423 dH/dT 42.2423 |
| gibbs_duhem | ok | 8.8e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 8.8e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 6.8e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: validated 2026-11-04: 5 of 8 Gao points pass; misses are bubble T +0.5..+0.57% or y +0.024, assessed. Evidence (re-measured 2026-11-04): L1 = the shared CoolProp pure-hydrocarbon points (mix-pure-*; the rule collapses to its host cubic on a pure feed, so the polar MeOH/H2O pure points carry the host's untranslated liquid-density/Cp misses, assessed above); L2 = the full Gao et al. 2012 MeOH/H2O 101.325 kPa isobar (mix-meohh2o-*, 8 points). The Bayer 1927 312.91 K point is also missed by the validated nrtl row (data quality).

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE table, for example, has no methanol subgroup)

## L1/L2 reference-case outcomes

29/43 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `lcvm-pure-MeOH-305K` — coolprop:Methanol
- `lcvm-pure-MeOH-330K` — coolprop:Methanol
- `lcvm-pure-H2O-340K` — coolprop:Water
- `lcvm-pure-H2O-370K` — coolprop:Water
- `lcvm-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `mix-pure-nC4-280K` — coolprop:n-Butane
- `mix-meohh2o-101.325kPa-366.0K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-361.35K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-356.95K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-353.25K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-346.20K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-343.31K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-341.20K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `mix-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22

## References

- Boukouvalas, C., Spiliotis, N., Coutsikos, P., Tzouvaras, N. & Tassios, D., Fluid Phase Equilib. 92, 75-106, 1994
- Michelsen, M. L., Fluid Phase Equilib. 60, 213-219, 1990
