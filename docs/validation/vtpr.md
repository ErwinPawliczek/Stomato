# vtpr — VTPR (Twu-alpha PR host + residual-gE rule over VTPR-UNIFAC)

family `mixing` · status **validated** · adapter `ngdesign.thermo.mixing_rules:PRVTPRThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–5e+07 Pa
- phases: V, L, VLL

## Parameters

- source: VTPR (Ahlers & Gmehling 2001): PR-family host with thermo's generalised Twu alpha and the VTPR residual-gE mixing rule (1/0.53087) over the VTPR-UNIFAC residual group model (thermo unifac_vtpr variant, VTPRSG/VTPRIP, version 3 - no combinatorial contribution)
- provenance: Ahlers, J. & Gmehling, J., "Development of an universal group contribution equation of state: 1. Prediction of liquid densities and of vapor-liquid equilibria", Fluid Phase Equilib. 191-192, 177-188, 2001; k_ij-free form - the gE model carries all interaction information. Declared deviations of the hosted form: linear covolume mixing (the paper's power-mean combining) and the generalised Twu alpha (the fitted Ahlers-Gmehling Twu table is not openly available)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 2.8e-16 | 380K/50000Pa T_ph 0 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 0 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 7.3e-08 | 380K/50000Pa vapor cp 42.2589 dH/dT 42.2589 |
| gibbs_duhem | ok | 8.9e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 6.4e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 8.9e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: validated 2026-11-04: 5 of 8 Gao points pass. single_liquid_limit runs the row-level MeOH/H2O feed because the family default uses EtOH, which the curated VTPR-UNIFAC map does not cover (first-use refusal). The C1/H2O points pass only through the wide 0.02 absolute band (x_C1 ~ 2e-3), not counted as evidence. Evidence (re-measured 2026-11-04): L1 = the shared CoolProp pure-hydrocarbon points (mix-pure-*; the rule collapses to its host cubic on a pure feed, so the polar MeOH/H2O pure points carry the host's untranslated liquid-density/Cp misses, assessed above); L2 = the full Gao et al. 2012 MeOH/H2O 101.325 kPa isobar (mix-meohh2o-*, 8 points). The Bayer 1927 312.91 K point is also missed by the validated nrtl row (data quality).

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C2 (74-84-0) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE table, for example, has no methanol subgroup)

## L1/L2 reference-case outcomes

30/45 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `vtpr-pure-MeOH-305K` — coolprop:Methanol
- `vtpr-pure-MeOH-330K` — coolprop:Methanol
- `vtpr-pure-H2O-340K` — coolprop:Water
- `vtpr-pure-H2O-370K` — coolprop:Water
- `vtpr-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `vtpr-c1h2o-310.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `vtpr-c1h2o-310.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
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

- Ahlers, J. & Gmehling, J., Fluid Phase Equilib. 191-192, 177-188, 2001
