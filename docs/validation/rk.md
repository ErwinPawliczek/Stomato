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
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@600K ok |
| round_trip | ok | 1.7e-15 | 350K/3.447e+06Pa T_ph 1.6e-16 H 1.7e-15 T_ps 3.2e-16 |
| dhdT_cp | ok | 4.9e-07 | 350K/3.447e+06Pa vapor cp 47.3918 dH/dT 47.3918 |
| gibbs_duhem | ok | 4.7e-08 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 4.7e-08; ['C1', 'CO2']@250K/2e+06Pa vapor 2.4e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: Two family-default L0 probes are moved, not excluded (measured 2026-11-04). phase_identification probes water at 600 K instead of 300 K: the check brackets the databank Psat by 0.5x/2x, and RK's own (Tr^-0.5 alpha) water vapour pressure at 300 K is 4.63x the databank value, so at 2x databank Psat the EOS-stable phase is correctly vapour; at 600 K the ratio is 1.15 and the bracket is a real classification test (nC4 300 K ratio 1.38, C3 300 K 1.15). gibbs_duhem probes the C1/C3 liquid at z(C1) = 0.5 instead of 0.6: RK's C1/C3 liquid root ceases to exist at z(C1) ~ 0.605 (250 K, 2 MPa), so the default loop over 0.59-0.61 integrated across a liquid/vapour root switch rather than along one root.

### L4 cross-model pairs

- n/a — l4_excluded: RK's databank-anchored alpha overpredicts the 293.15 K slice dew pressure ~16x versus the modern-EOS band (measured 1.18e7 vs 6.2e5-7.2e5 Pa) - the documented RK crudeness recorded in l0_excluded, an EOS-accuracy difference rather than a catalogue inconsistency.
- vs `api`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615893 Pa (rel 0.294) at 293.15 K.
- vs `kabadi`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 643917 Pa (rel 0.262) at 293.15 K.
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 716949 vs 872333 (rel 0.178); rhoV 6.08095 vs 7.41427 (rel 0.18); band 20%
- vs `pr`: ok — dew P 716949 vs 872333 (rel 0.178); rhoV 6.08095 vs 7.41427 (rel 0.18); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 717355 vs 872333 (rel 0.178); rhoV 6.08993 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.07898 vs 7.41427 (rel 0.18); band 20%
- vs `pr`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `pr78`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- vs `prsv`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- vs `prsv2`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- vs `rks`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- vs `sour`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08845 vs 7.41427 (rel 0.179); band 20%
- vs `sour`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614968 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: The Zudkevitch-Joffe Psat-fitted alpha with Omega_b held at the RK constant (documented deviation in params.alpha_parameters) runs +26-32% above the generalised-omega srk-family rows on the multi-component slice dew (measured 872333 vs 614968-643917 Pa at 293.15 K) while the pr-family rows sit within the 20% band (rel 0.17-0.18) - an alpha-accuracy difference, declared here rather than loosening the band.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: VLE is the srk row's, so the pair carries the srk / zudkevitch-joffe-rk slice dew gap declared on that row (measured 614969 vs 872333 Pa, rel 0.295)
- vs `srk`: ok — n/a — l4_excluded: The same slice dew gap the srk row declares against zudkevitch-joffe-rk (the Zudkevitch-Joffe alpha), unchanged by the zero k_ij: measured 614952 vs 872333 Pa (rel 0.295) at 293.15 K, srk itself 614969 Pa.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — n/a — l4_excluded: VLE is the srk row's, so the pair carries the srk / zudkevitch-joffe-rk slice dew gap declared on that row (measured 614969 vs 872333 Pa, rel 0.295)
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
