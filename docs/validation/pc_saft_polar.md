# pc_saft_polar — Polar PC-SAFT (hand-rolled kernel)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:PCSaftPolarThermo`.

## Applicability (Carlson 1996)

- component classes: polar_organic, hydrocarbon
- polar: True · electrolyte: False
- T window: 230–520 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: hand-rolled PC-SAFT + Gross & Vrabec dipolar kernel, feos-curated G&V 2006 parameters (data/thermo_params/saft/pure.yaml)
- provenance: physical term (hard chain + dispersion) is the teqp-pinned reimplementation shared with pc_saft_assoc; dipolar term from Gross & Vrabec (2006) AIChE J. 52, 1194-1204 eqs. 8-14 (Padé [2/3]) with closed-form density and composition derivatives; the a/b/c universal coefficients typed from the feos source (feos-org/feos, BSD-3, 11 printed digits, retrieved 2026-10-23) and cross-checked digit by digit against teqp's and CoolProp's 7-digit constants (all 45 agree); the Debye-to-reduced-unit conversion is computed from exact SI constants (1e-19/kB = 7242.9705...) matching teqp/feos, not CoolProp's hardcoded 7242.7029... (37 ppm lower, inside the case bands); fluid parameters from feos's curated copy of the paper's Table 2 (gross2006.json — acetone and DME, both non-associating, one dipolar segment each); quadrupolar fluids (CO2, Gross 2005) stay unbound pending resolution of an open-source sign discrepancy in the J_QQQ,3ijk c0[0] constant; k_ij = 0 (the paper introduces no binary interaction parameter for the bound slate). Non-polar partners (val-saft2, 2026-11-09) take the pc_saft row's Gross & Sadowski (2001) Table 1 set with mu = 0 (no quadrupole for CO2, exactly as the pc_saft row), so the dipolar term acts on the polar species only

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | ACETONE@329.44K bubble 0 dew 0; ACETONE@400K bubble 0 dew 0; DME@248K bubble 0 dew 0; DME@320K bubble 0 dew 0 |
| phase_identification | ok | 0 | ACETONE@350K ok; DME@280K ok |
| round_trip | ok | 3.4e-07 | 300K/300000Pa T_ph 1.1e-07 H 1.2e-07 T_ps 9.2e-08; 450K/100000Pa T_ph 9.9e-08 H 3.4e-07 T_ps 1.2e-07 |
| dhdT_cp | ok | 0 | 400K/100000Pa vapor cp 92.7286 dH/dT 92.7286 |
| gibbs_duhem | ok | 1e-08 | ['ACETONE', 'DME']@350K/300000Pa vapor 1e-08 |
| single_liquid_limit | ok | 0 | 300K/300000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 400K/100000Pa |

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified pc_saft parameters for ['H2O', 'N2', 'iC4', 'iC5']; supported: ['C1', 'C2', 'C3', 'C6+', 'CO2', 'binary_kij', 'excluded', 'nC4', 'nC5'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

41/60 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-ACETONE-296.0K-ps` — coolprop:Acetone
- `pure-ACETONE-350.0K-ps` — coolprop:Acetone
- `pure-ACETONE-400.0K-ps` — coolprop:Acetone
- `pure-ACETONE-450.0K-ps` — coolprop:Acetone
- `pure-DME-248.0K-ps` — coolprop:DimethylEther
- `pure-DME-280.0K-ps` — coolprop:DimethylEther
- `pure-DME-320.0K-ps` — coolprop:DimethylEther
- `pure-DME-360.0K-ps` — coolprop:DimethylEther
- `c3dme-313.19K-x0.0201` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.0384` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.0689` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.1303` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.2013` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.2909` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.4324` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.4945` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.5509` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.6061` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.667` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.7319` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.7762` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.8216` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.8623` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.9075` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.9616` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.9775` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.9812` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09
- `c3dme-313.19K-x0.9862` — Horstmann, Birke & Fischer (2004) Vapor-Liquid Equilibrium and Excess Enthalpy Data for the Binary Systems Propane + Dimethyl Ether and Propene + Dimethyl Ether at Temperatures from (298 to 323) K, J. Chem. Eng. Data 49, 38-42, DOI 10.1021/je0301242; propane + DME isotherm 313.19 K, static method P-x (NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1021/je0301242.xml data set 2); retrieved 2026-11-09

## References

- Gross & Vrabec, "An equation of state contribution for polar components: Dipolar molecules", AIChE J. 52 (2006) 1194-1204 (term background)
