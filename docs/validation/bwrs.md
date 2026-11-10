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
| round_trip | ok | 0 | 300K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 3.1e-07 | 300K/1e+06Pa vapor cp 36.707 dH/dT 36.707 |
| gibbs_duhem | ok | 6.9e-09 | ['C1', 'N2']@300K/5e+06Pa vapor 5.6e-09; ['C1', 'CO2']@220K/5e+06Pa hc_liquid 6.9e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/5e+06Pa |

Note: In-house BWRS: imperial parameter evaluation, SI at the boundary. Ideal-gas reference H_ig(298.15 K) = 0, S_ig(298.15 K, 1 bar) = 0 (with ideal mixing entropy). 2026-11-04 fixes: the departure enthalpy was returned in psia-ft3/lbmol and read as H/(RT) (saturated-liquid Cp came out ~ -4e4 J/(mol K)); the entropy departure lacked ln Z; the mixture dew SS stepped P the wrong way and the bubble incipient vapour was a one-step K at the feed. After the fixes the three pure saturation states pass every property (Cp within 2-3 %) and y_C1 passes at every C1/C3 point, while the k_ij = 0 bubble pressure misses +3.9 to +8.9 % at four of six points (assessed). Held provisional deliberately: the rule's letter is met (L1 pass, two L2 points pass) but the passing new L2 point sits at 2.99 %, inside a systematic over-prediction; a C1-C3 interaction parameter is the follow-up. Low-Tr states (C1 95 K, C2 110 K) also miss (Psat -20 % at C2 110 K) and are not bound.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: BWRSPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

21/25 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `bwr_ls-C1-155.0K` — coolprop:CH4
- `bwr_ls-C2-230.0K` — coolprop:C2H6
- `bwr_ls-C3-300.0K` — coolprop:C3H8
- `bwrs-c1c3-277.59K-3.103MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 270, table 'Experimental values', T = 277.59 K, P = 31.03 x 1e5 Pa, x_CH4 = 0.1695, y_CH4 = 0.7677; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-294.26K-2.068MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 270, table 'Experimental values', T = 294.26 K, P = 20.68 x 1e5 Pa, x_CH4 = 0.0749, y_CH4 = 0.5338; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-310.93K-4.137MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 310.93 K, P = 41.37 x 1e5 Pa, x_CH4 = 0.163, y_CH4 = 0.5714; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-327.59K-2.413MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 327.59 K, P = 24.13 x 1e5 Pa, x_CH4 = 0.0289, y_CH4 = 0.1663; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04
- `bwrs-c1c3-344.26K-4.137MPa` — Reamer, H. H., Sage, B. H., Lacey, W. N., Ind. Eng. Chem. 42, 534-539, 1950, as compiled in IUPAC Solubility Data Series vol. 27/28 (Methane), printed p. 271, table 'Experimental values', T = 344.26 K, P = 41.37 x 1e5 Pa, x_CH4 = 0.0813, y_CH4 = 0.2392; https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf, retrieved 2026-11-04

## References

- Starling, K. E., 'Fluid Thermodynamic Properties for Light Petroleum Systems', Gulf Publishing, 1973 (the BWRS equation and parameter basis)
- Starling, K. E., Cox, K. W., Kwok, Y. C., et al., 'Modified BWR Equation of State Parameters for Twenty-Seven Compounds', ORO-5249-2 (U.S. ERDA report), Table 5, 1976 - the parameter table transcribed for the ten registry-reachable compounds (methane and nitrogen rows verified against the report; reported methane fits: vapor pressure 0.44% AAD, density 0.32% AAD)
