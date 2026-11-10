# kabadi-danner-srk — SRK, Kabadi-Danner water-hydrocarbon mixing

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:KabadiDannerSrkThermo`.

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
| round_trip | ok | 1.6e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 1.6e-16 |
| dhdT_cp | ok | 4.7e-07 | 350K/3.447e+06Pa vapor cp 47.6308 dH/dT 47.6308 |
| gibbs_duhem | ok | 2.3e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2.3e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.8e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: Water-dependent a'' terms and k_wj; on water-free cases the row is plain SRK.

## L1/L2 reference-case outcomes

18/47 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `kabadi-danner-srk-pure-C1-125K` — coolprop:CH4
- `kabadi-danner-srk-pure-C3-300K` — coolprop:Propane
- `kabadi-danner-srk-pure-nC4-280K` — coolprop:n-Butane
- `kabadi-danner-srk-pure-CO2-265K` — coolprop:CO2
- `kabadi-danner-srk-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `kabadi-danner-srk-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `kabadi-danner-srk-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `kabadi-danner-srk-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `kabadi-danner-srk-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
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

- Kabadi, V. N.; Danner, R. P. A Modified Soave-Redlich-Kwong Equation of State for Water-Hydrocarbon Systems. Ind. Eng. Chem. Process Des. Dev. 1985, 24 (3), 537-541.
- Aspen Technology, Aspen Physical Property System - Physical Property Methods and Models, chapter 2, SRK-Kabadi-Danner, pp. 47-48 (equations and group-contribution table).
