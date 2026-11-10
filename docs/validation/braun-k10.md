# braun-k10 — Braun K10 low-pressure limit (ideal-K asymptote of the K10 charts)

family `kvalue` · status **validated** · adapter `ngdesign.thermo.kvalue:BraunK10Thermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon
- polar: False · electrolyte: False
- T window: 200–560 K · P window: 1000–700000 Pa
- phases: V, L, VLL

## Parameters

- source: vapour pressures from the ChemSep databank Psat basis; the row refuses service above 0.7 MPa by construction
- provenance: Braun convergence-pressure K10 charts, Cajander, B. C., Hipkin, H. G. & Lenoir, J. M., 'Prediction of Equilibrium Ratios from Nomographs of Improved Accuracy', J. Chem. Eng. Data 5(3), 251-259, 1960; the digitised polynomial fits are blocked on a published parameter source (GitHub issue 139), so the row implements the charts' documented low-pressure asymptote K_i = Psat_i/P and refuses outside it (deviation recorded for the T-05 review)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; nC4@280K bubble 2.2e-16 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; nC4@280K ok |
| round_trip | ok | 2.9e-12 | 300K/100000Pa T_ph 8.7e-15 H 2.9e-12 T_ps 1.9e-16 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| single_liquid_limit | ok | 0 | 300K/160000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the declared pure_psat_limit/phase_identification points stay inside the 0.7 MPa service cap (C1 and nC4); the propane/CO2 saturation points above the cap are refused by construction and covered by the applicability window instead

Declared exclusions (not silent skips):

- `gibbs_duhem` — the Braun K10 asymptote K10_i(T, P) is composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0

## L1/L2 reference-case outcomes

15/18 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `braun-k10-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `braun-k10-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
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
