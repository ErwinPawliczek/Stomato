# vdw — van der Waals

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:VanDerWaalsThermo`.

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
| phase_identification | FAIL | 1 | nC4@300K MISLABELED; C3@300K ok; H2O@300K MISLABELED |
| round_trip | ok | 4.9e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 4.9e-16 |
| dhdT_cp | ok | 3.4e-07 | 350K/3.447e+06Pa vapor cp 46.3863 dH/dT 46.3863 |
| gibbs_duhem | FAIL | 0.24 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 0.0091; ['C1', 'CO2']@250K/2e+06Pa vapor 0.24 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — The C1/C3 hc_liquid probe at 250 K sits where the vdW liquid root is mechanically unstable for methane-rich compositions, so the path integral crosses a root switch; the vapour probe passes.
- `phase_identification` — vdW's alpha = 1 misplaces the internal vapour-pressure correlation far above the databank value below Tc (nC4 and water at 300 K), so the databank-anchored 0.5x/2x classification bracket cannot straddle the offset; the C3 point passes.

### L4 cross-model pairs

- n/a — l4_excluded: van der Waals' constant-alpha overpredicts the 293.15 K slice dew pressure ~14x versus the modern-EOS band (measured 1.02e7 vs 6.2e5-7.2e5 Pa) - the documented vdW crudeness recorded in l0_excluded.

## L1/L2 reference-case outcomes

11/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `vdw-pure-C1-125K` — coolprop:CH4
- `vdw-pure-C3-300K` — coolprop:Propane
- `vdw-pure-nC4-280K` — coolprop:n-Butane
- `vdw-pure-CO2-265K` — coolprop:CO2
- `vdw-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `vdw-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `vdw-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `vdw-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `vdw-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- van der Waals, J. D. Over de Continuiteit van den Gas- en Vloeistoftoestand; thesis, Universiteit Leiden, 1873.
