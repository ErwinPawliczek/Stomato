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

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Wilson, G. M., J. Am. Chem. Soc. 86(2), 127-130, 1964
- Siimer, E., Kirss, H., Kuus, M. & Kudryavtseva, L., Proc. Estonian Acad. Sci. Chem. 51(1), 19-28, 2002, doi 10.3176/chem.2002.1.02
- Kirss, H., Kuus, M., Siimer, E. & Kudryavtseva, L., Proc. Estonian Acad. Sci. Chem. 51(4), 215-224, 2002, doi 10.3176/chem.2002.4.03
