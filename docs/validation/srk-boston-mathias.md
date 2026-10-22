# srk-boston-mathias — Soave-Redlich-Kwong, Boston-Mathias alpha

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:SrkBostonMathiasThermo`.

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
| dhdT_cp | ok | 4.5e-07 | 350K/3.447e+06Pa vapor cp 47.5923 dH/dT 47.5923 |
| gibbs_duhem | ok | 1.6e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 1.6e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.7e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

## L1/L2 reference-case outcomes

16/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `srk-boston-mathias-pure-C1-125K` — coolprop:CH4
- `srk-boston-mathias-pure-C3-300K` — coolprop:Propane
- `srk-boston-mathias-pure-nC4-280K` — coolprop:n-Butane
- `srk-boston-mathias-pure-CO2-265K` — coolprop:CO2
- `srk-boston-mathias-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `srk-boston-mathias-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `srk-boston-mathias-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `srk-boston-mathias-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `srk-boston-mathias-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- Boston, J. F.; Mathias, P. M. Phase Equilibria in a Third-Parameter Equation of State. Proc. 2nd Int. Conf. Phase Equilibria and Fluid Properties in the Chemical Process Industries, West Berlin, 1980; pp 39-48.
- Peng, D.-Y.; Robinson, D. B. A New Two-Constant Equation of State. Ind. Eng. Chem. Fundam. 1976, 15 (1), 59-64.
- Soave, G. Equilibrium Constants from a Modified Redlich-Kwong Equation of State. Chem. Eng. Sci. 1972, 27 (6), 1197-1203.
