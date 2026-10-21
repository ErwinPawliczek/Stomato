# bwrs — BWRS (Starling 1973) natural-gas components

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.helmholtz:BWRSPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 95–600 K · P window: 1000–7e+07 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; N2@110K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@160K ok; N2@110K ok |
| round_trip | ok | 4e-16 | 300K/5e+06Pa T_ph 1.9e-16 H 4e-16 T_ps 1.9e-16 |
| dhdT_cp | ok | 4.7e-09 | 300K/1e+06Pa vapor cp 2434.77 dH/dT 2434.77 |
| gibbs_duhem | ok | 6.9e-09 | ['C1', 'N2']@300K/5e+06Pa vapor 5.6e-09; ['C1', 'CO2']@220K/5e+06Pa hc_liquid 6.9e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/5e+06Pa |

Note: In-house BWRS: imperial parameter evaluation, SI at the boundary. Ideal-gas reference H_ig(298.15 K) = 0, S_ig(298.15 K, 1 bar) = 0. The pure-C1 saturation sweep cases stay pending: the BWRS vapor-pressure fit (1973 databasis) does not reproduce modern references within the 3% tolerance at all declared points, and the file keeps them registered for the L1 follow-up.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: BWRSPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., 'Fluid Thermodynamic Properties for Light Petroleum Systems', Gulf Publishing, 1973 (the BWRS equation and parameter basis)
- Starling, K. E., Cox, K. W., Kwok, Y. C., et al., 'Modified BWR Equation of State Parameters for Twenty-Seven Compounds', ORO-5249-2 (U.S. ERDA report), Table 5, 1976 - the parameter table transcribed for the ten registry-reachable compounds (methane and nitrogen rows verified against the report; reported methane fits: vapor pressure 0.44% AAD, density 0.32% AAD)
