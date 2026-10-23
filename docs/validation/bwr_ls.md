# bwr_ls — BWR-Lee-Starling (BWRS parameter basis, Han-Starling mixing, provisional)

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.bwr:BWRLeeStarlingPackage`.

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

Note: Provisional: reuses the merged BWRS parameter-dictionary equations with the Han-Starling generalized mixing law. The k_ij table ships deliberately empty - no verifiable open C1/C3 Lee-Starling interaction set was found - and with the table empty the mixing law reduces exactly to the one used by the bwrs row, which is the row's only tested claim; the k_ij dependence itself is unvalidated. Component constants are the ORO-5249-2 Table 5 set cited on the bwrs row. Measured results: at the three bound pure-fluid saturation points (C1 155 K, C2 230 K, C3 300 K) bubble/dew pressures and vapour/liquid densities track CoolProp closely, while Cp comes out large and negative (assessed per case above) - the shared BWRS parameter-evaluation Cp defect, made visible by binding the cases rather than excluding Cp. The bound near-pure-propane C1/C3 VLE point (277.59 K, 0.689 MPa) misses literature bubble_P by 1.24% and vapour composition by 0.50%; the higher-pressure isotherm point (1.724 MPa) measured 4.73% and 56.03% and stays unbound pending a mixing-rule decision.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: BWRLeeStarlingPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

14/17 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `bwr_ls-C1-155.0K` — coolprop:CH4
- `bwr_ls-C2-230.0K` — coolprop:C2H6
- `bwr_ls-C3-300.0K` — coolprop:C3H8
- `bwr_ls-c1c3-277.59K` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20

## References

- Lee, B. I., Starling, K. E., Starling's BWR equation variant as summarized in 'Thermodynamic Property Prediction of Light Hydrocarbons and Related Fluids' (the equation form)
- Starling, K. E., 'Fluid Thermodynamic Properties for Light Petroleum Systems', Gulf Publishing, 1973 (the parameter dictionary the row evaluates)
- Han, B.-H., Starling, K. E., 'Generalized Correlation for the Densities of Multicomponent Light Hydrocarbon Mixtures', AIChE J. 18, 380-384, 1972 (the generalized mixing law; the row ships an empty k_ij table)
- Starling, K. E. et al., 'Fluid Thermodynamic Property Data for Light Petroleum Systems' / OSTI report ORO-5249-2 (1976), Table 5 (the component parameter dictionary the row evaluates, shared with the bwrs row)
