# nrtl_tdep_hoc — NRTL T-dependent form + Hayden-O'Connell vapour

family `gamma_phi` · status **validated** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water
- polar: True · electrolyte: False
- T window: 300–420 K · P window: 1000–1e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/nrtl/tdep_pairs.yaml
- provenance: tau_ij = a_ij + b_ij / T from the IUPAC 2011-037-2-100 preliminary methanol + water selection, with per-entry provenance in the file; the only pair the row covers, any other refuses

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.4e-14 | 380K/50000Pa T_ph 0 H 0 T_ps 7.5e-16; 400K/100000Pa T_ph 9.5e-15 H 4.4e-14 T_ps 5.4e-15 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 44.3086 dH/dT 44.3086 |
| gibbs_duhem | ok | 9e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 9e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

## L1/L2 reference-case outcomes

28/30 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `nrtl-ig-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `nrtl-ig-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `nrtl-ig-pure-H2O-340K` — coolprop:Water
- `nrtl-ig-pure-H2O-370K` — coolprop:Water
- `nrtl-ig-pure-MeOH-305K` — coolprop:Methanol
- `nrtl-ig-pure-MeOH-330K` — coolprop:Methanol
- `unifac-meohh2o-66.52kPa-xMeOH0.246` — Yang, Sun, Ma, Yin & Zeng (2012) "Organic Salt Effect on Vapor-Liquid Equilibrium of the Methanol + Water System at Subatmospheric Pressure", J. Chem. Eng. Data 57, 2696-2701, doi:10.1021/je300613v; salt-free methanol + water series, recirculating-still T-x, y by gas chromatography, 66.52 kPa; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je300613v.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 1 (vapour mole fraction: set 2); retrieved 2026-11-04
- `unifac-meohh2o-66.52kPa-xMeOH0.535` — Yang, Sun, Ma, Yin & Zeng (2012) "Organic Salt Effect on Vapor-Liquid Equilibrium of the Methanol + Water System at Subatmospheric Pressure", J. Chem. Eng. Data 57, 2696-2701, doi:10.1021/je300613v; salt-free methanol + water series, recirculating-still T-x, y by gas chromatography, 66.52 kPa; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je300613v.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 1 (vapour mole fraction: set 2); retrieved 2026-11-04
- `unifac-meohh2o-66.52kPa-xMeOH0.705` — Yang, Sun, Ma, Yin & Zeng (2012) "Organic Salt Effect on Vapor-Liquid Equilibrium of the Methanol + Water System at Subatmospheric Pressure", J. Chem. Eng. Data 57, 2696-2701, doi:10.1021/je300613v; salt-free methanol + water series, recirculating-still T-x, y by gas chromatography, 66.52 kPa; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je300613v.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 1 (vapour mole fraction: set 2); retrieved 2026-11-04

## References

- Renon, H. & Prausnitz, J. M., AIChE J. 14(1), 135-144, 1968
- IUPAC Project 2011-037-2-100, Supporting Information 1 (VLE), preliminary selection
