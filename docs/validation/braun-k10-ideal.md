# braun-k10-ideal — BK10 with ideal enthalpies

family `kvalue` · status **validated** · adapter `ngdesign.thermo.kvalue:BraunK10IdealThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon
- polar: False · electrolyte: False
- T window: 200–560 K · P window: 1000–700000 Pa
- phases: V, L, VLL

## Parameters

- source: vapour pressures, heats of vaporisation and ideal-gas heat capacities from the ChemSep databank; the row refuses service above 0.7 MPa by construction, as braun-k10 does
- provenance: K-values as the braun-k10 row (Cajander, Hipkin & Lenoir 1960, low-pressure asymptote K_i = Psat_i/P); enthalpy basis ideal-gas vapour and ideal liquid H_L = sum x_i (H_ig_i - dHvap_i), no Lee-Kesler departure

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; nC4@280K bubble 2.2e-16 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; nC4@280K ok |
| round_trip | ok | 2.8e-13 | 350K/100000Pa T_ph 0 H 0 T_ps 2.8e-13 |
| dhdT_cp | ok | 3.5e-09 | 350K/100000Pa vapor cp 124.223 dH/dT 124.223 |
| single_liquid_limit | ok | 0 | 300K/160000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the round-trip and Cp points use a subcritical pair because the ideal liquid is undefined for a component above its critical temperature (the braun-k10 row's C1/C3 point has C1 at 300 K)

Declared exclusions (not silent skips):

- `gibbs_duhem` — the K10 asymptote is composition-independent, as for braun-k10: the Gibbs-Duhem residual is identically zero and the check's normalisation degenerates to 0/0

## L1/L2 reference-case outcomes

11/14 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `idealk-pure-toluene-101.3kPa` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData dataset 11 (toluene vapour pressure 101.3 kPa at T = 383.4 K); retrieved 2026-11-04
- `idealk-pure-o-xylene-101.3kPa` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData dataset 14 (o-xylene vapour pressure 101.3 kPa at T = 417.5 K); retrieved 2026-11-04
- `idealk-pure-heptane-101.3kPa` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData dataset 8 (heptane vapour pressure 101.3 kPa at T = 371.4 K); retrieved 2026-11-04
- `idealk-pure-nonane-101.3kPa` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData dataset 2 (nonane vapour pressure 101.3 kPa at T = 423.8 K); retrieved 2026-11-04
- `idealk-toluene-o-xylene-101.3kPa-x0.693` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData datasets 15/16 (toluene + o-xylene), x_toluene = 0.693, T = 390.5 K, y_toluene = 0.886; retrieved 2026-11-04
- `idealk-toluene-o-xylene-101.3kPa-x0.5` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData datasets 15/16 (toluene + o-xylene), x_toluene = 0.5, T = 396.3 K, y_toluene = 0.765; retrieved 2026-11-04
- `idealk-toluene-o-xylene-101.3kPa-x0.23` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData datasets 15/16 (toluene + o-xylene), x_toluene = 0.23, T = 407.0 K, y_toluene = 0.436; retrieved 2026-11-04
- `idealk-nonane-heptane-101.3kPa-x0.367` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData datasets 21/22 (nonane + heptane), x_nonane = 0.367, T = 382.3 K, y_nonane = 0.084; retrieved 2026-11-04
- `idealk-nonane-heptane-101.3kPa-x0.641` — Gupta, B. S., Lee, M.-J., 'Isobaric vapor-liquid equilibrium for binary systems of toluene + o-xylene, benzene + o-xylene, nonane + benzene and nonane + heptane at 101.3 kPa', Fluid Phase Equilib. 352, 86-92, 2013, doi:10.1016/j.fluid.2013.05.016; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.fluid.2013.05.016.xml, PureOrMixtureData datasets 21/22 (nonane + heptane), x_nonane = 0.641, T = 396.2 K, y_nonane = 0.274; retrieved 2026-11-04

## References

- Cajander, B. C., Hipkin, H. G. & Lenoir, J. M., J. Chem. Eng. Data 5(3), 251-259, 1960
- Smith, J. M., Van Ness, H. C. & Abbott, M. M., Introduction to Chemical Engineering Thermodynamics, 7th ed., McGraw-Hill, 2005 (ideal-solution model)
