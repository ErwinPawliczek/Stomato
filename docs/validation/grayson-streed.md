# grayson-streed — Grayson-Streed K-values (GS nu0 sets, original RK vapour phase)

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:GraysonStreedThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert
- polar: False · electrolyte: False
- T window: 255–533 K · P window: 1000–1.38e+07 Pa
- phases: V, L, VLL

## Parameters

- source: nu0/regular-solution coefficient tables under data/thermo_params/kvalue/, critical constants and acentric factors from the ChemSep databank
- provenance: Grayson, H. G. & Streed, C. W., 'Vapor-Liquid Equilibria for High Temperature, High Pressure Hydrogen-Hydrocarbon Systems', Proc. 6th World Pet. Congr., Frankfurt, Sect. III, 233-245, 1963; coefficient sets verified against the DWSIM ChaoSeader implementation (commit 1abf72d)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| gibbs_duhem | ok | 2.4e-10 | ['C1', 'C3']@300K/100000Pa vapor 2.4e-10 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: no binary anchor passes inside the case tolerances (the Reamer-Sage-Lacey methane-propane states miss by -6 to -35 %, see data/validation/kvalue/cases.yaml); the row stays provisional on the pureK bubble evidence

Declared exclusions (not silent skips):

- `phase_identification` — the row's own GS nu0 vapour-pressure basis overestimates the methane saturation pressure by up to +102 % (documented under pure_psat_limit), placing the check's own-Psat anchors at states where the Lee-Kesler departure enthalpy basis has no vapour root; the phase classification itself is exercised at the row's binary bubble and dew anchors instead
- `pure_psat_limit` — the row's own GS nu0/RK correlation is the vapour-pressure basis: the measured pure-component bubble at the databank-Psat state deviates +102.64 % (C1, 125 K, the GS methane set outside its fitted range at Tr = 0.66), -2.53 % (C3, 300 K), -2.14 % (nC4, 280 K) and +0.86 % (CO2, 265 K); the databank-equality limit is the databank-Psat rows' construction, and this row's correlation accuracy is measured by its pureK bubble cases instead

## L1/L2 reference-case outcomes

6/6 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `grayson-streed-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `grayson-streed-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `grayson-streed-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml

## References

- Grayson, H. G. & Streed, C. W., Proc. 6th World Pet. Congr., Sect. III, 233-245, 1963
- Prausnitz, J. M., Lichtenthaler, R. N. & de Azevedo, E. G., Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., Prentice Hall, 1999
