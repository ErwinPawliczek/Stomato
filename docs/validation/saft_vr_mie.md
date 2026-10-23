# saft_vr_mie — SAFT-VR Mie (teqp)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:SaftVrMieThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, acid_gas
- polar: False · electrolyte: False
- T window: 90–420 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp SAFT-VR-Mie, explicit coefficients (data/thermo_params/saft/pure.yaml)
- provenance: m, sigma, lambda_r, lambda_a from Lafitte, Apostolakis, Essmann & Muller (2013) J. Chem. Phys. 139, 154504 (DOI 10.1063/1.4819786), cross-checked against teqp 0.23.2's compiled parameter values to printed precision (methane, ethane, propane); CO2 from the same Table III (p. 154504-25), typed and checked digit-for-digit against the paper PDF in T-18. N2 stays absent — Lafitte (2013) Table III carries no nitrogen row and no other verified citable table was found (secondary sources attribute an N2 set to this table that it does not contain); k_ij = 0 for the pairs in scope

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@150K bubble 0 dew 0; C2@200K bubble 0 dew 0; C3@250K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@150K ok; C3@250K ok |
| round_trip | ok | 1.5e-07 | 150K/4e+06Pa T_ph 9.8e-08 H 7.5e-08 T_ps 9.4e-08; 180K/300000Pa T_ph 1e-07 H 1.5e-07 T_ps 8.8e-08 |
| dhdT_cp | ok | 0 | 180K/300000Pa vapor cp 34.2376 dH/dT 34.2376 |
| gibbs_duhem | ok | 4.5e-08 | ['C1', 'C3']@250K/500000Pa vapor 4.5e-08 |
| single_liquid_limit | ok | 0 | 150K/4e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 250K/500000Pa |

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified saft_vr_mie parameters for ['C6+', 'H2O', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']; supported: ['C1', 'C2', 'C3', 'CO2'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

47/56 comparisons pass. Failing comparisons are assessed in the
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
- `c1co2-293.130K-6.135MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-293.130K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 293.13 K isotherm; retrieved 2026-10-21
- `c1co2-298.142K-6.976MPa` — Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML, doi 10.1016/j.fluid.2018.01.011, 298.14 K isotherm; retrieved 2026-10-21

## References

- Lafitte, Apostolakis, Essmann & Muller, "Development of the truncated perturbed chain-polar SAFT... ", J. Chem. Phys. 139 (2013) 154504
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
