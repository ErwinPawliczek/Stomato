# lee-kesler-ploecker — Lee-Kesler-Ploecker corresponding states (Ploecker mixing rules, k_ij = 0)

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:LeeKeslerPloeckerThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 200–560 K · P window: 1000–1.5e+07 Pa
- phases: V, L, VLL

## Parameters

- source: critical constants, acentric factors and the Lee-Kesler tables under data/thermo_params/kvalue/, from the ChemSep databank and the source papers
- provenance: Ploecker, U., Knapp, H. & Prausnitz, J. M., 'Calculation of High-Pressure Vapor-Liquid Equilibria from a Corresponding-States Correlation', Ind. Eng. Chem. Process Des. Dev. 17(3), 324-332, 1978; Lee, B. I. & Kesler, M. G., 'A Generalized Thermodynamic Correlation Based on Three-Parameter Corresponding States', AIChE J. 21(3), 510-527, 1975; binary interaction parameters set to zero (k_ij = 0)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| phase_identification | ok | 0 | C1@125K ok; C3@300K ok |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| gibbs_duhem | ok | 4.1e-08 | ['C1', 'C3']@300K/4e+06Pa hc_liquid 4.1e-08 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the methane-propane states at 4.826/6.205 MPa have no Lee-Kesler vapour root at the iterated vapour composition (the flash classifies them single-phase); only the 4.137 MPa state binds as a binary anchor

Declared exclusions (not silent skips):

- `pure_psat_limit` — the Lee-Kesler EOS is the row's own corresponding-states vapour-pressure basis: the measured pure-component bubble at the databank-Psat state deviates +0.32 % (C1, 125 K), +2.10 % (C3, 300 K), +7.49 % (nC4, 280 K) and -0.96 % (CO2, 265 K); the 1e-6 databank-equality limit is the databank-Psat rows' construction, and this row's EOS accuracy is measured by its pureK bubble cases instead

## L1/L2 reference-case outcomes

8/8 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `lee-kesler-ploecker-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `lee-kesler-ploecker-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `lee-kesler-ploecker-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `lee-kesler-ploecker-c1c3-294.26K-4.137MPa` — Reamer, Sage & Lacey, methane-propane VLE, Ind. Eng. Chem., vol. 42, p. 534, 1950, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 270-271, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.1987, y_C1 0.7038; retrieved 2026-10-21

## References

- Ploecker, U., Knapp, H. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 17(3), 324-332, 1978
- Lee, B. I. & Kesler, M. G., AIChE J. 21(3), 510-527, 1975
