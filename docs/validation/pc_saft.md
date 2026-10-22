# pc_saft — PC-SAFT (teqp)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:PCSaftThermo`.

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

Note: T-15 disposition: teqp 0.23.2 ships cp312 wheels and CI runs Python 3.12, so the pending SAFT cases are runnable in CI (the local py3.13 gap is a sandbox fact, not a CI one). Promotion stays blocked on the measured misses: pure saturated-liquid Cp and CO2 saturation pressure outside tolerance (Gross & Sadowski 2001 parameters verified; T-07), and the MeOH/H2O crash. The row keeps experimental status until an association term or refit lands.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

Declared case ids:

- `pure-C1-95.3K` — coolprop:CH4
- `pure-C1-125.0K` — 
- `pure-C1-155.0K` — 
- `pure-C1-172.0K` — 
- `pure-C1-181.0K` — 
- `pure-CO2-216.7K` — coolprop:CO2
- `pure-CO2-240.0K` — coolprop:CO2
- `pure-CO2-265.0K` — coolprop:CO2
- `pure-CO2-285.0K` — coolprop:CO2
- `pure-CO2-288.9K` — coolprop:CO2
- `c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-293.130K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 298.14 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-7.508MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 298.14 K isotherm; retrieved 2026-10-21
- `c1co2-303.145K-7.306MPa` — 
- `c1co2-303.144K-7.361MPa` — 

## References

- Gross & Sadowski, "Perturbed-Chain SAFT: An Equation of State Based on a Perturbation Theory for Chain Molecules", Ind. Eng. Chem. Res. 40 (2001) 1244-1257
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
