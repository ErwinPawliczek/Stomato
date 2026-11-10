# glycol_pr — Glycol package (TEG dehydration, tuned PR)

family `cubic` · status **validated** · adapter `ngdesign.thermo.cubic:GlycolPrThermo`.

## Applicability (Carlson 1996)

- component classes: water, glycol, light_gas, hydrocarbon
- polar: True · electrolyte: False
- T window: 283.15–480 K · P window: 10000–1.5e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/glycol/teg_water_pr.yaml
- provenance: Gironi, Maschietti & Piemonte 2007, k12(T) linear in T and their Ambrose TEG constants, with per-entry provenance in the file. MEG refuses, its open CPA and k_ij values carry no primary citation; other pairs keep the ChemSep PR table

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 4.9e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 4.9e-16 |
| dhdT_cp | ok | 4.7e-07 | 350K/3.447e+06Pa vapor cp 47.62 dH/dT 47.6201 |
| gibbs_duhem | ok | 2e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.7e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: The derivatives contract's dlnphi_dT and dlnphi_dP stay plain PR's and omit the tuned k_ij. Dry streams flash as pr does.

### L4 cross-model pairs

- n/a — l4_excluded: the TEG constants replace the databank's only for TEG and the slice feed carries no glycol, so the row's slice point is the pr row's and adds no independent L4 information

## L1/L2 reference-case outcomes

33/41 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cubicopt-pure-C1-125K` — coolprop:CH4
- `cubicopt-pure-C3-300K` — coolprop:Propane
- `cubicopt-pure-nC4-280K` — coolprop:n-Butane
- `cubicopt-pure-CO2-265K` — coolprop:CO2
- `cubicopt-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `cubicopt-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `teg-h2o-85kPa-xw0.117` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.161` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.242` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.325` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.41` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.543` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.704` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.826` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04
- `teg-h2o-85kPa-xw0.915` — Mostafazadeh, Rahimpour & Shariati (2009) Vapor-Liquid Equilibria of Water + Triethylene Glycol (TEG) and Water + TEG + Toluene at 85 kPa, J. Chem. Eng. Data 54(3), 876-881, doi:10.1021/je800675u; NIST TRC ThermoML file 10.1021/je800675u.xml, data sets 1 (boiling T vs x_water) and 2 (y_water vs x_water) at 85 kPa; retrieved 2026-11-04

## References

- Gironi, F.; Maschietti, M.; Piemonte, V. Modelling triethylene glycol - water system for natural gas dehydration. ICheaP-8, 2007
