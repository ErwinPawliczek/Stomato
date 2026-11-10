# kabadi-danner-free-water — Water/hydrocarbon free-water method (Kabadi-Danner + NBS)

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:KabadiDannerFreeWaterThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water
- polar: False · electrolyte: False
- T window: 273.16–640 K · P window: 1000–1e+08 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep) for the EOS; chemicals.iapws for IAPWS-95
- provenance: Kabadi-Danner SRK as the kabadi-danner-srk row. The free-water phase uses IAPWS-95, which superseded the NBS/NRC 1984 steam tables the plan names; the Haar-Gallagher-Kell formulation itself is not implemented

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 1.6e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 1.6e-16 |
| dhdT_cp | ok | 4.7e-07 | 350K/3.447e+06Pa vapor cp 47.6308 dH/dT 47.6308 |
| gibbs_duhem | ok | 2.3e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2.3e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.8e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

## L1/L2 reference-case outcomes

29/79 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `cubicopt-pure-C1-125K` — coolprop:CH4
- `cubicopt-pure-C3-300K` — coolprop:Propane
- `cubicopt-pure-nC4-280K` — coolprop:n-Butane
- `cubicopt-pure-CO2-265K` — coolprop:CO2
- `cubicopt-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `cubicopt-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `aq-n2h2o-dew-282.86K-607kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=282.86 K, P=607 kPa, y_H2O=0.00204; retrieved 2026-11-09
- `aq-n2h2o-dew-282.99K-1799kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=282.99 K, P=1799 kPa, y_H2O=0.000714; retrieved 2026-11-09
- `aq-n2h2o-dew-282.99K-3036kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=282.99 K, P=3036 kPa, y_H2O=0.000446; retrieved 2026-11-09
- `aq-n2h2o-dew-283.03K-4408kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=283.03 K, P=4408 kPa, y_H2O=0.000317; retrieved 2026-11-09
- `aq-n2h2o-dew-293.1K-558kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=293.1 K, P=558 kPa, y_H2O=0.00425; retrieved 2026-11-09
- `aq-n2h2o-dew-293.1K-2991kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=293.1 K, P=2991 kPa, y_H2O=0.000844; retrieved 2026-11-09
- `aq-n2h2o-dew-293.1K-4810kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=293.1 K, P=4810 kPa, y_H2O=0.000558; retrieved 2026-11-09
- `aq-n2h2o-dew-293.19K-1828kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=293.19 K, P=1828 kPa, y_H2O=0.00136; retrieved 2026-11-09
- `aq-n2h2o-dew-304.02K-578kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=304.02 K, P=578 kPa, y_H2O=0.00793; retrieved 2026-11-09
- `aq-n2h2o-dew-304.36K-1257kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=304.36 K, P=1257 kPa, y_H2O=0.0037; retrieved 2026-11-09
- `aq-n2h2o-dew-304.51K-2539kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=304.51 K, P=2539 kPa, y_H2O=0.00188; retrieved 2026-11-09
- `aq-n2h2o-dew-304.61K-4638kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=304.61 K, P=4638 kPa, y_H2O=0.00112; retrieved 2026-11-09
- `aq-n2h2o-dew-313.15K-1246kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=313.15 K, P=1246 kPa, y_H2O=0.00609; retrieved 2026-11-09
- `aq-n2h2o-dew-313.16K-4781kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=313.16 K, P=4781 kPa, y_H2O=0.00175; retrieved 2026-11-09
- `aq-n2h2o-dew-313.26K-2836kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=313.26 K, P=2836 kPa, y_H2O=0.00278; retrieved 2026-11-09
- `aq-n2h2o-dew-313.3K-498kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=313.3 K, P=498 kPa, y_H2O=0.0153; retrieved 2026-11-09
- `aq-n2h2o-dew-322.88K-499kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=322.88 K, P=499 kPa, y_H2O=0.024; retrieved 2026-11-09
- `aq-n2h2o-dew-322.93K-3397kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=322.93 K, P=3397 kPa, y_H2O=0.00396; retrieved 2026-11-09
- `aq-n2h2o-dew-322.93K-4841kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=322.93 K, P=4841 kPa, y_H2O=0.00292; retrieved 2026-11-09
- `aq-n2h2o-dew-323.1K-1420kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=323.1 K, P=1420 kPa, y_H2O=0.00872; retrieved 2026-11-09
- `aq-n2h2o-dew-332.45K-1448kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=332.45 K, P=1448 kPa, y_H2O=0.0134; retrieved 2026-11-09
- `aq-n2h2o-dew-332.52K-461kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=332.52 K, P=461 kPa, y_H2O=0.0427; retrieved 2026-11-09
- `aq-n2h2o-dew-332.52K-2454kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=332.52 K, P=2454 kPa, y_H2O=0.00855; retrieved 2026-11-09
- `aq-n2h2o-dew-332.52K-4358kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=332.52 K, P=4358 kPa, y_H2O=0.00488; retrieved 2026-11-09
- `aq-n2h2o-dew-342.31K-425kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=342.31 K, P=425 kPa, y_H2O=0.0719; retrieved 2026-11-09
- `aq-n2h2o-dew-342.31K-462kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=342.31 K, P=462 kPa, y_H2O=0.0658; retrieved 2026-11-09
- `aq-n2h2o-dew-342.31K-4962kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=342.31 K, P=4962 kPa, y_H2O=0.00666; retrieved 2026-11-09
- `aq-n2h2o-dew-342.39K-1466kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=342.39 K, P=1466 kPa, y_H2O=0.0219; retrieved 2026-11-09
- `aq-n2h2o-dew-342.42K-2899kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=342.42 K, P=2899 kPa, y_H2O=0.0103; retrieved 2026-11-09
- `aq-n2h2o-dew-351.87K-540kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=351.87 K, P=540 kPa, y_H2O=0.0849; retrieved 2026-11-09
- `aq-n2h2o-dew-351.92K-2957kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=351.92 K, P=2957 kPa, y_H2O=0.0162; retrieved 2026-11-09
- `aq-n2h2o-dew-351.95K-4797kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=351.95 K, P=4797 kPa, y_H2O=0.0111; retrieved 2026-11-09
- `aq-n2h2o-dew-352.12K-1480kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=352.12 K, P=1480 kPa, y_H2O=0.0335; retrieved 2026-11-09
- `aq-n2h2o-dew-363K-555kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=363 K, P=555 kPa, y_H2O=0.126; retrieved 2026-11-09
- `aq-n2h2o-dew-363.08K-4874kPa` — Mohammadi, Chapoy, Tohidi & Richon (2005) Water Content Measurement and Modeling in the Nitrogen + Water System, J. Chem. Eng. Data 50, 541-545, doi:10.1021/je049676q; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je049676q.xml, data set 1 (gas-phase water mole fraction vs T, P), row T=363.08 K, P=4874 kPa, y_H2O=0.0161; retrieved 2026-11-09
- `aq-c6h2o-lle-303.95K-700kPa` — Marche, Ferronato & Jose (2003) Solubilities of n-Alkanes (C6 to C8) in Water from 30 C to 180 C, J. Chem. Eng. Data 48, 967-971, doi:10.1021/je025659u; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je025659u.xml, data set 1 (hexane mole fraction in the aqueous liquid, constraint P = 700 kPa), row T=303.95 K, x=2.06e-06; retrieved 2026-11-09
- `aq-c6h2o-lle-343.45K-700kPa` — Marche, Ferronato & Jose (2003) Solubilities of n-Alkanes (C6 to C8) in Water from 30 C to 180 C, J. Chem. Eng. Data 48, 967-971, doi:10.1021/je025659u; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je025659u.xml, data set 1 (hexane mole fraction in the aqueous liquid, constraint P = 700 kPa), row T=343.45 K, x=2.77e-06; retrieved 2026-11-09
- `aq-c6h2o-lle-373.75K-700kPa` — Marche, Ferronato & Jose (2003) Solubilities of n-Alkanes (C6 to C8) in Water from 30 C to 180 C, J. Chem. Eng. Data 48, 967-971, doi:10.1021/je025659u; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je025659u.xml, data set 1 (hexane mole fraction in the aqueous liquid, constraint P = 700 kPa), row T=373.75 K, x=6.16e-06; retrieved 2026-11-09
- `aq-c1h2o-310.9K-2.28MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-310.9K-6.55MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-310.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-310.9K-24.37MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-310.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-310.9K-68.22MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-2.28MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-6.50MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-12.96MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-24.37MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-344.3K-68.02MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-2.32MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-6.49MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-24.51MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `aq-c1h2o-410.9K-67.81MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20

## References

- Wagner, W.; Pruss, A. J. Phys. Chem. Ref. Data 2002, 31, 387
- Kabadi, V. N.; Danner, R. P. Ind. Eng. Chem. Process Des. Dev. 1985, 24, 537
- Aspen Technology, Aspen Physical Property System - Physical Property Methods and Models, chapter 2, SRK-Kabadi-Danner, pp. 47-48 (equations and group-contribution table).
