# pr-lee-kesler-enthalpy — Peng-Robinson, Lee-Kesler enthalpies

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:PrLeeKeslerThermo`.

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
| round_trip | ok | 4.9e-16 | 350K/3.447e+06Pa T_ph 1.6e-16 H 0 T_ps 4.9e-16 |
| dhdT_cp | ok | 0 | 350K/3.447e+06Pa vapor cp 47.3241 dH/dT 47.3241 |
| gibbs_duhem | ok | 2e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.7e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

## L1/L2 reference-case outcomes

21/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pr-lee-kesler-enthalpy-pure-C1-125K` — coolprop:CH4
- `pr-lee-kesler-enthalpy-pure-C3-300K` — coolprop:Propane
- `pr-lee-kesler-enthalpy-pure-nC4-280K` — coolprop:n-Butane
- `pr-lee-kesler-enthalpy-pure-CO2-265K` — coolprop:CO2
- `pr-lee-kesler-enthalpy-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `pr-lee-kesler-enthalpy-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `pr-lee-kesler-enthalpy-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `pr-lee-kesler-enthalpy-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `pr-lee-kesler-enthalpy-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- Lee, B. I.; Kesler, M. G. A Generalized Thermodynamic Correlation Based on Three-Parameter Corresponding States. AIChE J. 1975, 21 (3), 510-527.
