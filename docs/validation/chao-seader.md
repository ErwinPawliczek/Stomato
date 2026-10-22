# chao-seader — Chao-Seader K-values (nu0 + regular solution + Redlich-Kwong)

family `kvalue` · status **validated** · adapter `ngdesign.thermo.kvalue:ChaoSeaderThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 200–530 K · P window: 1000–1.4e+07 Pa
- phases: V, L, VLL

## Parameters

- source: nu0/regular-solution coefficient tables under data/thermo_params/kvalue/, critical constants and acentric factors from the ChemSep databank
- provenance: Chao, K. C. & Seader, J. D., 'A General Correlation of Vapor-Liquid Equilibria in Hydrocarbon Mixtures', AIChE J. 7(4), 598-605, 1961; nu0 coefficient sets verified against the DWSIM ChaoSeader implementation (commit 1abf72d) after re-transcription from the Rust DWSIM-kernel port; solubility parameters and molar volumes from Prausnitz, Lichtenthaler & de Azevedo, Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., 1999

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| phase_identification | ok | 0 | C1@125K ok; C3@300K ok; nC4@280K ok |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| gibbs_duhem | ok | 2.4e-10 | ['C1', 'C3']@300K/100000Pa vapor 2.4e-10 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Declared exclusions (not silent skips):

- `pure_psat_limit` — the row's own nu0/RK correlation is the vapour-pressure basis: the measured pure-component bubble at the databank-Psat state deviates +11.74 % (C1, 125 K), -4.87 % (C3, 300 K), -2.21 % (nC4, 280 K) and -3.28 % (CO2, 265 K); the 1e-6 databank-equality limit is the databank-Psat rows' construction, and this row's correlation accuracy is measured by its pureK bubble cases instead

## L1/L2 reference-case outcomes

10/10 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `chao-seader-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `chao-seader-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `chao-seader-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `chao-seader-c1c3-277.59K-4.826MPa` — Reamer, Sage & Lacey, methane-propane VLE, Ind. Eng. Chem., vol. 42, p. 534, 1950, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 270-271, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.2834, y_C1 0.8135; retrieved 2026-10-21
- `chao-seader-c1c3-294.26K-4.137MPa` — Reamer, Sage & Lacey, methane-propane VLE, Ind. Eng. Chem., vol. 42, p. 534, 1950, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 270-271, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.1987, y_C1 0.7038; retrieved 2026-10-21

## References

- Chao, K. C. & Seader, J. D., AIChE J. 7(4), 598-605, 1961
- Prausnitz, J. M., Lichtenthaler, R. N. & de Azevedo, E. G., Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., Prentice Hall, 1999
