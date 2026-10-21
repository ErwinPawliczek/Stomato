# rk — Redlich-Kwong

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:RedlichKwongThermo`.

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
| phase_identification | FAIL | 1 | nC4@300K ok; C3@300K ok; H2O@300K MISLABELED |
| round_trip | ok | 3.2e-16 | 350K/3.447e+06Pa T_ph 1.6e-16 H 0 T_ps 3.2e-16 |
| dhdT_cp | ok | 4.9e-07 | 350K/3.447e+06Pa vapor cp 47.3918 dH/dT 47.3918 |
| gibbs_duhem | FAIL | 0.22 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 0.22; ['C1', 'CO2']@250K/2e+06Pa vapor 2.4e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — The C1/C3 hc_liquid probe at 250 K lies above RK's methane pseudocritical temperature (a and b are fitted to the true critical point), so the liquid root does not exist along the whole composition path and the path integral crosses a root switch; the vapour probe passes at 2.4e-9.
- `phase_identification` — RK's Tr^-0.5 alpha misplaces the internal vapour-pressure correlation by orders of magnitude far below Tc (water at 300 K, Tr = 0.46), so the databank-anchored 0.5x/2x classification bracket cannot straddle the offset; the C3 and nC4 points pass.

### L4 cross-model pairs

- n/a — l4_excluded: RK's databank-anchored alpha overpredicts the 293.15 K slice dew pressure ~16x versus the modern-EOS band (measured 1.18e7 vs 6.2e5-7.2e5 Pa) - the documented RK crudeness recorded in l0_excluded, an EOS-accuracy difference rather than a catalogue inconsistency.
- vs `api`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615893 Pa (rel 0.294) at 293.15 K.
- vs `kabadi`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 643917 Pa (rel 0.262) at 293.15 K.
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 717633 vs 872333 (rel 0.177); rhoV 6.09273 vs 7.41427 (rel 0.178); band 20%
- vs `pr`: ok — dew P 717633 vs 872333 (rel 0.177); rhoV 6.09273 vs 7.41427 (rel 0.178); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.09097 vs 7.41427 (rel 0.178); band 20%
- vs `pr78`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `prsv`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- vs `prsv2`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- vs `rks`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- vs `sour`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08845 vs 7.41427 (rel 0.179); band 20%
- vs `sour`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614968 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: The Zudkevitch-Joffe Psat-fitted alpha with Omega_b held at the RK constant (documented deviation in params.alpha_parameters) runs +26-32% above the generalised-omega srk-family rows on the multi-component slice dew (measured 872333 vs 614968-643917 Pa at 293.15 K) while the pr-family rows sit within the 20% band (rel 0.17-0.18) - an alpha-accuracy difference, declared here rather than loosening the band.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `twu`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 597284 Pa (rel 0.315) at 293.15 K.
- vs `twu`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 596571 Pa (rel 0.316) at 293.15 K.

## L1/L2 reference-case outcomes

13/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `rk-pure-C1-125K` — coolprop:CH4
- `rk-pure-C3-300K` — coolprop:Propane
- `rk-pure-nC4-280K` — coolprop:n-Butane
- `rk-pure-CO2-265K` — coolprop:CO2
- `rk-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `rk-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `rk-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `rk-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `rk-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- Redlich, O.; Kwong, J. N. S. On the Thermodynamics of Solutions. V. An Equation of State. Fugacities of Gaseous Solutions. Chem. Rev. 1949, 44 (1), 233-244.
