# cosmo_sac_ig — COSMO-SAC (sigma profiles)

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 273.15–450 K · P window: 1000–1e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/cosmo_sac/profiles.yaml
- provenance: COSMO-SAC 2010 (Hsieh, Sandler & Lin 2010) with the constants of Bell et al. 2020 Table 2; three-profile (NHB/OH/OT) sigma profiles of the UD database copied unmodified from usnistgov/COSMOSAC profiles/UD/sigma3 (commit 1b82456b, retrieved 2026-11-04; academic/non-profit licence, shipped under the 2026-11-04 deferred-licence decision). No fitted binary parameters - a predictive model; the Hsieh 2014 dispersion term is not included. Only the shipped components resolve; any other refuses

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.4e-16 | 380K/50000Pa T_ph 1.5e-16 H 4.1e-16 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 4.4e-16 T_ps 1.4e-16 |
| dhdT_cp | ok | 6e-08 | 380K/50000Pa vapor cp 42.0432 dH/dT 42.0432 |
| gibbs_duhem | ok | 1.5e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.5e-08 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no COSMO-SAC sigma profile for C1 (74-82-8) in data/thermo_params/cosmo_sac/profiles.yaml; refusing to predict

## L1/L2 reference-case outcomes

10/18 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cosmo-sac-ig-pure-MeOH-330K` — coolprop:Methanol
- `cosmo-sac-ig-pure-H2O-370K` — coolprop:Water
- `nrtl-ig-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `nrtl-ig-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `nrtl-ig-meohnc4-323.22K-0.3366MPa` — Courtial, Soo, Coquelet, Paricaud, Ramjugernath & Richon (2009) Fluid Phase Equilib. 277, pp. 152-161, Table 4, 323.22 K isotherm; retrieved 2026-10-21
- `nrtl-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21

## References

- Hsieh, C.-M., Sandler, S. I. & Lin, S.-T., Fluid Phase Equilib. 297, 90-97, 2010
- Bell, I. H., Mickoleit, E., Hsieh, C.-M., Lin, S.-T., Vrabec, J., Breitkopf, C. & Jaeger, A., J. Chem. Theory Comput. 16(4), 2635-2646, 2020, doi:10.1021/acs.jctc.9b01016
- Hsieh, C.-M., Lin, S.-T. & Vrabec, J., Fluid Phase Equilib. 367, 109-116, 2014 (Table 6 benchmark ln gamma infinite-dilution values, as transcribed in usnistgov/COSMOSAC tests/catch_tests.cpp)
