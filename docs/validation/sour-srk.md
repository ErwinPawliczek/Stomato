# sour-srk — Soave-Redlich-Kwong, sour-water correction

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:SourSrkThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water
- polar: False · electrolyte: False
- T window: 90–700 K · P window: 1000–2e+08 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep)
- provenance: Kooijman & Taylor, ChemSep IPDB; critical constants and acentric factors from the ChemSep pure-component database; binary interaction parameters from the 'ChemSep PR' table, 0 where the table has no pair

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 3.2e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 3.2e-16 |
| dhdT_cp | ok | 4.8e-07 | 350K/3.447e+06Pa vapor cp 47.6557 dH/dT 47.6557 |
| gibbs_duhem | ok | 2.3e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2.3e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.8e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: Aqueous-only; identical to srk off water-rich roots.

## L1/L2 reference-case outcomes

17/73 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `sour-srk-pure-C1-125K` — coolprop:CH4
- `sour-srk-pure-C3-300K` — coolprop:Propane
- `sour-srk-pure-nC4-280K` — coolprop:n-Butane
- `sour-srk-pure-CO2-265K` — coolprop:CO2
- `sour-srk-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `sour-srk-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `sour-srk-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `sour-srk-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `sour-srk-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `aq-co2h2o-300.95K-2071kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=300.95 K, P=2071 kPa, x=0.01099; retrieved 2026-11-09
- `aq-co2h2o-300.95K-4782kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=300.95 K, P=4782 kPa, x=0.02032; retrieved 2026-11-09
- `aq-co2h2o-300.95K-7837kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=300.95 K, P=7837 kPa, x=0.02335; retrieved 2026-11-09
- `aq-co2h2o-300.95K-19445kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=300.95 K, P=19445 kPa, x=0.02696; retrieved 2026-11-09
- `aq-co2h2o-300.95K-34753kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=300.95 K, P=34753 kPa, x=0.0296; retrieved 2026-11-09
- `aq-co2h2o-307.79K-1292kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=1292 kPa, x=0.00601; retrieved 2026-11-09
- `aq-co2h2o-307.79K-1310kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=1310 kPa, x=0.00601; retrieved 2026-11-09
- `aq-co2h2o-307.79K-2243kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=2243 kPa, x=0.00974; retrieved 2026-11-09
- `aq-co2h2o-307.79K-3380kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=3380 kPa, x=0.01384; retrieved 2026-11-09
- `aq-co2h2o-307.79K-4594kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=4594 kPa, x=0.01704; retrieved 2026-11-09
- `aq-co2h2o-307.79K-5543kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=5543 kPa, x=0.01931; retrieved 2026-11-09
- `aq-co2h2o-307.79K-7143kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=7143 kPa, x=0.02228; retrieved 2026-11-09
- `aq-co2h2o-307.79K-12231kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=12231 kPa, x=0.02414; retrieved 2026-11-09
- `aq-co2h2o-307.79K-19236kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=307.79 K, P=19236 kPa, x=0.02589; retrieved 2026-11-09
- `aq-co2h2o-322.62K-2991kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=2991 kPa, x=0.00961; retrieved 2026-11-09
- `aq-co2h2o-322.62K-4778kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=4778 kPa, x=0.01279; retrieved 2026-11-09
- `aq-co2h2o-322.62K-5486kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=5486 kPa, x=0.01493; retrieved 2026-11-09
- `aq-co2h2o-322.62K-8667kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=8667 kPa, x=0.01959; retrieved 2026-11-09
- `aq-co2h2o-322.62K-20727kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=20727 kPa, x=0.02394; retrieved 2026-11-09
- `aq-co2h2o-322.62K-40349kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=322.62 K, P=40349 kPa, x=0.02708; retrieved 2026-11-09
- `aq-co2h2o-373.39K-3515kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=373.39 K, P=3515 kPa, x=0.00697; retrieved 2026-11-09
- `aq-co2h2o-373.39K-7941kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=373.39 K, P=7941 kPa, x=0.01286; retrieved 2026-11-09
- `aq-co2h2o-373.39K-19340kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=373.39 K, P=19340 kPa, x=0.02112; retrieved 2026-11-09
- `aq-co2h2o-373.39K-42077kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=373.39 K, P=42077 kPa, x=0.02578; retrieved 2026-11-09
- `aq-co2h2o-423.48K-2631kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=423.48 K, P=2631 kPa, x=0.00327; retrieved 2026-11-09
- `aq-co2h2o-423.48K-5109kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=423.48 K, P=5109 kPa, x=0.00665; retrieved 2026-11-09
- `aq-co2h2o-423.48K-9772kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=423.48 K, P=9772 kPa, x=0.0117; retrieved 2026-11-09
- `aq-co2h2o-423.48K-19549kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=423.48 K, P=19549 kPa, x=0.02063; retrieved 2026-11-09
- `aq-co2h2o-423.48K-40690kPa` — Ahmadi & Chapoy (2018) CO2 solubility in formation water under sequestration conditions, Fluid Phase Equilib. 463, 80-90, doi:10.1016/j.fluid.2018.02.002; NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2018.02.002.xml, data set 1 (CO2 + pure water, CO2 mole fraction in the liquid), row T=423.48 K, P=40690 kPa, x=0.02839; retrieved 2026-11-09
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

- American Petroleum Institute, API Publication 955, sour-water equilibrium (Wilson) model; documentation as EPA-600/2-80-067, 'Design guide: sour water systems' ionisation framework.
- Wilson, G. M. A Modified Redlich-Kwong Equation of State, Application to General Physical Data Calculations. AIChE 65th National Meeting, Cleveland, 1969, Paper 15C.
