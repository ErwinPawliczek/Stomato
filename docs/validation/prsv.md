# prsv — Peng-Robinson-Stryjek-Vera (PRSV)

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:PrsvThermo`.

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
| round_trip | ok | 4.9e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 4.9e-16 |
| dhdT_cp | ok | 4.7e-07 | 350K/3.447e+06Pa vapor cp 47.6236 dH/dT 47.6236 |
| gibbs_duhem | ok | 2.1e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2.1e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.7e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

### L4 cross-model pairs

- vs `api`: ok — dew P 615893 vs 724017 (rel 0.149); rhoV 5.18815 vs 6.14587 (rel 0.156); band 20%
- vs `kabadi`: ok — dew P 643917 vs 724017 (rel 0.111); rhoV 5.42979 vs 6.14587 (rel 0.117); band 20%
- vs `pr`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- vs `pr`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- vs `pr`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- vs `pr`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- vs `pr`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.07898 vs 6.14587 (rel 0.0109); band 20%
- vs `pr78`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- vs `prsv2`: ok — dew P 724017 vs 724017 (rel 0); rhoV 6.14587 vs 6.14587 (rel 0); band 20%
- vs `rks`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- vs `sour`: ok — dew P 724017 vs 717386 (rel 0.00924); rhoV 6.14587 vs 6.08845 (rel 0.00943); band 20%
- vs `sour`: ok — dew P 724017 vs 614968 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `srk`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `srk`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- vs `srk`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `srk`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18231 (rel 0.186); band 20%
- vs `twu`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `twu`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `zudkevitch`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%

## L1/L2 reference-case outcomes

21/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `prsv-pure-C1-125K` — coolprop:CH4
- `prsv-pure-C3-300K` — coolprop:Propane
- `prsv-pure-nC4-280K` — coolprop:n-Butane
- `prsv-pure-CO2-265K` — coolprop:CO2
- `prsv-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `prsv-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `prsv-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `prsv-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `prsv-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- Stryjek, R.; Vera, J. H. PRSV: An Improved Peng-Robinson Equation of State for Pure Compounds and Mixtures. Can. J. Chem. Eng. 1986, 64 (2), 323-333 and 334-340.
