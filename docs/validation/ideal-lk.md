# ideal-lk — Ideal K-values with the Lee-Kesler departure enthalpy basis

family `kvalue` · status **validated** · adapter `ngdesign.thermo.kvalue:IdealRaoultThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water, alcohol, polar_organic
- polar: True · electrolyte: False
- T window: 90–620 K · P window: 1000–3e+06 Pa
- phases: V, L, VLL

## Parameters

- source: vapour pressures from the ChemSep databank Psat basis
- provenance: shares the ideal-raoult adapter and databank Psat basis; the row's named role is the Lee-Kesler departure enthalpy basis (the row options declare enthalpy lee_kesler), which is the KValuePackage implementation for every row of this family

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@280K bubble 2.2e-16 dew 0; CO2@265K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; C3@300K ok |
| round_trip | ok | 2.9e-12 | 300K/100000Pa T_ph 8.7e-15 H 2.9e-12 T_ps 1.9e-16 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the row shares the ideal-raoult adapter (databank Psat, K_i = Psat_i/P); the lee_kesler enthalpy declaration names the departure basis the plan assigns this row

Declared exclusions (not silent skips):

- `gibbs_duhem` — K_i = Psat_i/P is composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0; there is no composition dependence to probe

## L1/L2 reference-case outcomes

19/22 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ideal-lk-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
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

- Raoult, F.-M., Compt. Rend. 104, 1430-1433, 1887
- Lee, B. I. & Kesler, M. G., AIChE J. 21(3), 510-527, 1975 (departure basis)
