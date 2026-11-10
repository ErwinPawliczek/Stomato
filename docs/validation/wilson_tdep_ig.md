# wilson_tdep_ig — Wilson T-dependent form + ideal gas vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 319–424 K · P window: 20000–110000 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/wilson/tdep_pairs.yaml
- provenance: ln Lambda_ij = a_ij + b_ij / T from Siimer et al. 2002 (hexan-2-one / o-xylene / nonane) and Kirss et al. 2002 (toluene / p-xylene / 1,2-dichloroethane), Proc. Estonian Acad. Sci. Chem. 51, Table 4 of each, with per-pair provenance and the journal's licence wording in the file (no Creative Commons licence is named); pairs keyed by CAS, any other pair refuses

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | toluene@360K bubble 0 dew 0; p-xylene@380K bubble 0 dew 0 |
| phase_identification | ok | 0 | toluene@360K ok; p-xylene@420K ok |
| round_trip | ok | 6.8e-16 | 380K/50000Pa T_ph 1.5e-16 H 6.8e-16 T_ps 1.5e-16; 400K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.3e-07 | 420K/50000Pa vapor cp 160.549 dH/dT 160.549 |
| gibbs_duhem | ok | 1.1e-09 | ['p-xylene', 'toluene']@360K/100000Pa hc_liquid 1.1e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 320K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no temperature-dependent wilson parameters for pair C1 (74-82-8) / C2 (74-84-0) in data/thermo_params/wilson/tdep_pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix

## L1/L2 reference-case outcomes

12/21 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-pxylene-380K-gphi` — coolprop:p-Xylene
- `pure-toluene-350K-gphi` — coolprop:Toluene
- `pure-toluene-400K-gphi` — coolprop:Toluene
- `hasdemir2007-dcetol-101.3kPa-x0.27` — Hasdemir, M.; Uslu, H., Isobaric (vapour + liquid) equilibria data for the binary systems {1,2-dichloroethane (1) + toluene (2)} and {1,2-dichloroethane (1) + acetic acid (2)} at atmospheric pressure, J. Chem. Thermodyn. 39 (2007) 1189-1195, doi:10.1016/j.jct.2006.12.003; 101.3 kPa T-x-y, NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.jct.2006.12.003.xml PureOrMixtureData sets 7 (T) and 8 (y) at x_DCE=0.27; point rule x nearest 0.25/0.50/0.75 fixed before the run; retrieved 2026-11-09
- `hasdemir2007-dcetol-101.3kPa-x0.502` — Hasdemir, M.; Uslu, H., Isobaric (vapour + liquid) equilibria data for the binary systems {1,2-dichloroethane (1) + toluene (2)} and {1,2-dichloroethane (1) + acetic acid (2)} at atmospheric pressure, J. Chem. Thermodyn. 39 (2007) 1189-1195, doi:10.1016/j.jct.2006.12.003; 101.3 kPa T-x-y, NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.jct.2006.12.003.xml PureOrMixtureData sets 7 (T) and 8 (y) at x_DCE=0.502; point rule x nearest 0.25/0.50/0.75 fixed before the run; retrieved 2026-11-09
- `hasdemir2007-dcetol-101.3kPa-x0.745` — Hasdemir, M.; Uslu, H., Isobaric (vapour + liquid) equilibria data for the binary systems {1,2-dichloroethane (1) + toluene (2)} and {1,2-dichloroethane (1) + acetic acid (2)} at atmospheric pressure, J. Chem. Thermodyn. 39 (2007) 1189-1195, doi:10.1016/j.jct.2006.12.003; 101.3 kPa T-x-y, NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.jct.2006.12.003.xml PureOrMixtureData sets 7 (T) and 8 (y) at x_DCE=0.745; point rule x nearest 0.25/0.50/0.75 fixed before the run; retrieved 2026-11-09

## References

- Wilson, G. M., J. Am. Chem. Soc. 86(2), 127-130, 1964
- Siimer, E., Kirss, H., Kuus, M. & Kudryavtseva, L., Proc. Estonian Acad. Sci. Chem. 51(1), 19-28, 2002, doi 10.3176/chem.2002.1.02
- Kirss, H., Kuus, M., Siimer, E. & Kudryavtseva, L., Proc. Estonian Acad. Sci. Chem. 51(4), 215-224, 2002, doi 10.3176/chem.2002.4.03
