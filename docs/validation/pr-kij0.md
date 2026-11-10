# pr-kij0 — Peng-Robinson, zero k_ij

family `cubic` · status **provisional** · adapter `ngdesign.thermo.cubic:PrKij0Thermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 90–700 K · P window: 1000–2e+08 Pa
- phases: V, L

## Parameters

- source: thermo IPDB (ChemSep) pure-component constants; no binary table
- provenance: Kooijman & Taylor, ChemSep pure-component database for critical constants and acentric factors; every binary interaction parameter k_ij = 0. This is the zero-k_ij variant of the plain cubic EOS that textbook simulator examples ran (e.g. Seader, Henley & Roper, Separation Process Principles 3rd ed., Example 10.9, CHEMCAD SRK - its printed feed bubble point 123.5 F at 100 psia is reproduced with zero k_ij, not with the IPDB table). Use the IPDB-k_ij row for design work.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 1.6e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 1.6e-16 |
| dhdT_cp | ok | 4.8e-07 | 350K/3.447e+06Pa vapor cp 47.659 dH/dT 47.6591 |
| gibbs_duhem | ok | 1.6e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 1.6e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 3.4e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Peng, D.-Y. & Robinson, D. B., 'A New Two-Constant Equation of State', Ind. Eng. Chem. Fundam. 15(1), 59-64, 1976
