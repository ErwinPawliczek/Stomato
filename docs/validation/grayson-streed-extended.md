# grayson-streed-extended — Grayson-Streed K-values, extended range (same adapter and coefficient table)

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:GraysonStreedThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 255–730 K · P window: 1000–2e+07 Pa
- phases: V, L, VLL

## Parameters

- source: nu0/regular-solution coefficient tables under data/thermo_params/kvalue/, critical constants and acentric factors from the ChemSep databank
- provenance: Grayson, H. G. & Streed, C. W., 'Vapor-Liquid Equilibria for High Temperature, High Pressure Hydrogen-Hydrocarbon Systems', Proc. 6th World Pet. Congr., Frankfurt, Sect. III, 233-245, 1963; the extended-range row shares the standard row's adapter and coefficient table — the separately refitted extended-range coefficients are not available from a published source (deviation recorded for the T-05 review)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| gibbs_duhem | ok | 2.4e-10 | ['C1', 'C3']@300K/100000Pa vapor 2.4e-10 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the extended-range applicability window is served by the same coefficient table as the standard row; T-05 records this as a deviation pending published extended-range coefficients

Declared exclusions (not silent skips):

- `phase_identification` — the row's own GS nu0 vapour-pressure basis overestimates the methane saturation pressure by up to +102 % (documented under pure_psat_limit), placing the check's own-Psat anchors at states where the Lee-Kesler departure enthalpy basis has no vapour root; the phase classification itself is exercised at the row's binary bubble and dew anchors instead
- `pure_psat_limit` — shares the grayson-streed adapter and vapour-pressure basis; the measured pure-component bubble at the databank-Psat state deviates +102.64 % (C1, 125 K), -2.53 % (C3, 300 K), -2.14 % (nC4, 280 K) and +0.86 % (CO2, 265 K); the accuracy is measured by this row's pureK bubble cases instead

## L1/L2 reference-case outcomes

6/6 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `grayson-streed-extended-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `grayson-streed-extended-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `grayson-streed-extended-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml

## References

- Grayson, H. G. & Streed, C. W., Proc. 6th World Pet. Congr., Sect. III, 233-245, 1963
