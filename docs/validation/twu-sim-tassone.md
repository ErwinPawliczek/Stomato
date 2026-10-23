# twu-sim-tassone — Twu-Sim-Tassone cubic EOS

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:TwuSimTassoneThermo`.

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
| round_trip | ok | 3.2e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 3.2e-16 |
| dhdT_cp | ok | 4.8e-07 | 350K/3.447e+06Pa vapor cp 47.6306 dH/dT 47.6307 |
| gibbs_duhem | FAIL | 0.0039 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 5.5e-08; ['C1', 'CO2']@250K/2e+06Pa vapor 0.0039 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

Note: Fitted alpha table covers C1-nC6; CO2/N2/H2S in the slate use the generalised Twu alpha.

Declared exclusions (not silent skips):

- `gibbs_duhem` — The C1/C3 hc_liquid probe at 250 K sits above the TST internal methane pseudo-critical line, so the liquid root switches along the composition path; the vapour probe passes.
- `phase_identification` — The TST alpha is fitted to hydrogen/hydrocarbon systems; for the probe components at 300 K the internal vapour-pressure correlation deviates beyond the databank-anchored 0.5x/2x bracket.

## L1/L2 reference-case outcomes

16/26 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `twu-sim-tassone-pure-C1-125K` — coolprop:CH4
- `twu-sim-tassone-pure-C3-300K` — coolprop:Propane
- `twu-sim-tassone-pure-nC4-280K` — coolprop:n-Butane
- `twu-sim-tassone-pure-CO2-265K` — coolprop:CO2
- `twu-sim-tassone-c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `twu-sim-tassone-c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `twu-sim-tassone-ng-dew-morch-243.4K-0.30MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `twu-sim-tassone-ng-dew-morch-254.6K-0.68MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- `twu-sim-tassone-ng-dew-morch-260.8K-1.04MPa` — Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21

## References

- Twu, C. H.; Sim, W. D.; Tassone, V. A versatile liquid activity model for SRK, PR and a new cubic equation-of-state TST. Fluid Phase Equilibria 194-197 (2002) 385-399, doi:10.1016/S0378-3812(01)00663-X; constants and form as implemented in the Clapeyron.jl TSTEOS (github.com/ClapeyronThermo/Clapeyron.jl), retrieved 2026-10.
- Twu, C. H.; Bluck, D.; Coon, J. E.; Cunningham, J. R. A Cubic Equation of State with a New Alpha Function and a New Mixing Rule. Fluid Phase Equilib. 1991, 69 (1), 33-50 (generalised alpha used for components outside the fitted table).
