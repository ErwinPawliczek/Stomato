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
| round_trip | ok | 0 | 300K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 3.1e-07 | 300K/1e+06Pa vapor cp 36.707 dH/dT 36.707 |
| gibbs_duhem | ok | 6.9e-09 | ['C1', 'N2']@300K/5e+06Pa vapor 5.6e-09; ['C1', 'CO2']@220K/5e+06Pa hc_liquid 6.9e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/5e+06Pa |

Note: Provisional: reuses the merged BWRS parameter-dictionary equations with the Han-Starling generalized mixing law. The k_ij table ships deliberately empty, so the mixing law reduces exactly to the bwrs row and every number equals bwrs; the k_ij dependence itself is unvalidated. The saturated-liquid Cp defect was the shared BWRS departure-enthalpy unit bug, fixed 2026-11-04 (C1 155 K Cp 66.02 vs 67.61, -2.3 %). Held provisional for the same reason as bwrs: the C1/C3 bubble pressure is over-predicted by +3.9 to +8.9 % at four of six points without an interaction parameter (assessed); vapour compositions pass.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: BWRLeeStarlingPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

23/27 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `bwr_ls-C1-155.0K` — coolprop:CH4
- `bwr_ls-C2-230.0K` — coolprop:C2H6
- `bwr_ls-C3-300.0K` — coolprop:C3H8
- `bwr_ls-c1c3-277.59K` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `bwrs-c1c3-277.59K-3.103MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 270, table 'Experimental values', T = 277.59 K, P = 31.03 x 1e5 Pa, x_CH4 = 0.1695, y_CH4 = 0.7677; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-294.26K-2.068MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 270, table 'Experimental values', T = 294.26 K, P = 20.68 x 1e5 Pa, x_CH4 = 0.0749, y_CH4 = 0.5338; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-310.93K-4.137MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 310.93 K, P = 41.37 x 1e5 Pa, x_CH4 = 0.163, y_CH4 = 0.5714; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-327.59K-2.413MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 327.59 K, P = 24.13 x 1e5 Pa, x_CH4 = 0.0289, y_CH4 = 0.1663; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-344.26K-4.137MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 344.26 K, P = 41.37 x 1e5 Pa, x_CH4 = 0.0813, y_CH4 = 0.2392; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04

## References

- Lee, B. I., Starling, K. E., Starling's BWR equation variant as summarized in 'Thermodynamic Property Prediction of Light Hydrocarbons and Related Fluids' (the equation form)
- Starling, K. E., 'Fluid Thermodynamic Properties for Light Petroleum Systems', Gulf Publishing, 1973 (the parameter dictionary the row evaluates)
- Han, B.-H., Starling, K. E., 'Generalized Correlation for the Densities of Multicomponent Light Hydrocarbon Mixtures', AIChE J. 18, 380-384, 1972 (the generalized mixing law; the row ships an empty k_ij table)
- Starling, K. E. et al., 'Fluid Thermodynamic Property Data for Light Petroleum Systems' / OSTI report ORO-5249-2 (1976), Table 5 (the component parameter dictionary the row evaluates, shared with the bwrs row)
