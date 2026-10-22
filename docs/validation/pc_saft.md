# pc_saft — PC-SAFT (teqp)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:PCSaftThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, acid_gas
- polar: False · electrolyte: False
- T window: 95–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp PC-SAFT, explicit coefficients (data/thermo_params/saft/pure.yaml)
- provenance: m, sigma, epsilon/k from Gross & Sadowski (2001) Ind. Eng. Chem. Res. 40, 1244-1257 (methane, ethane, propane, n-butane, n-pentane, n-hexane) and Gross & Sadowski (2001) as reported in teqp's compiled library (CO2, cross-checked to teqp's compiled values to printed precision); k_ij = 0 — no verifiable open citation for the cited pairs' interaction parameters was found, and tuning k_ij against the validation points is forbidden

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@150K bubble 0 dew 0; C2@200K bubble 0 dew 0; nC4@250K bubble 0 dew 0; CO2@240K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@150K ok; nC4@300K ok; CO2@250K ok |
| round_trip | ok | 6e-07 | 150K/4e+06Pa T_ph 9.5e-08 H 7.2e-08 T_ps 9.8e-08; 250K/200000Pa T_ph 1.2e-07 H 6e-07 T_ps 9e-08 |
| dhdT_cp | ok | 0 | 250K/200000Pa vapor cp 34.5587 dH/dT 34.5587 |
| gibbs_duhem | ok | 3.9e-08 | ['C1', 'CO2']@250K/500000Pa vapor 3.9e-08; ['C1', 'C2']@150K/5e+06Pa hc_liquid 2.3e-08 |
| single_liquid_limit | ok | 0 | 150K/5e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 250K/500000Pa |

Note: T-15 disposition: teqp 0.23.2 ships cp312 wheels and CI runs Python 3.12, so the pending SAFT cases are runnable in CI (the local py3.13 gap is a sandbox fact, not a CI one). Promotion stays blocked on the measured misses: pure saturated-liquid Cp and CO2 saturation pressure outside tolerance (Gross & Sadowski 2001 parameters verified; T-07), and the MeOH/H2O crash. T-15c confirmed the CI-runnability on 2026-10-22 and promoted the row to provisional: all 16 bound cases measured, 44/62 comparisons pass, and every miss is declared per case in `assessed:` with the measured values — saturated-liquid Cp on all pure fluids (no explicit residual-Cp term in the chain EOS), CO2 saturation pressure 4.0-9.5 % high without a quadrupole term, and C1/CO2 binary bubble_P 5.7-7.5 % low with k_ij = 0.

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified pc_saft parameters for ['H2O', 'N2', 'iC4', 'iC5']; supported: ['C1', 'C2', 'C3', 'C6+', 'CO2', 'binary_kij', 'excluded', 'nC4', 'nC5'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

44/62 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-C1-95.3K` — coolprop:CH4
- `pure-C1-125.0K` — coolprop:CH4
- `pure-C1-155.0K` — coolprop:CH4
- `pure-C1-172.0K` — coolprop:CH4
- `pure-C1-181.0K` — coolprop:CH4
- `pure-CO2-216.7K` — coolprop:CO2
- `pure-CO2-240.0K` — coolprop:CO2
- `pure-CO2-265.0K` — coolprop:CO2
- `pure-CO2-285.0K` — coolprop:CO2
- `pure-CO2-288.9K` — coolprop:CO2
- `c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-293.130K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 298.14 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-7.508MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 298.14 K isotherm; retrieved 2026-10-21
- `c1co2-303.145K-7.306MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 303.14 K isotherm; retrieved 2026-10-21
- `c1co2-303.144K-7.361MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (10.1016/j.fluid.2018.01.011), 303.14 K isotherm; retrieved 2026-10-21

## References

- Gross & Sadowski, "Perturbed-Chain SAFT: An Equation of State Based on a Perturbation Theory for Chain Molecules", Ind. Eng. Chem. Res. 40 (2001) 1244-1257
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
