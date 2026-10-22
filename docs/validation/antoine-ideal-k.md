# antoine-ideal-k — Antoine-basis ideal K-values (K_i = Psat_i/P)

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:AntoineIdealKThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, water
- polar: True · electrolyte: False
- T window: 150–620 K · P window: 1000–3e+06 Pa
- phases: V, L, VLL

## Parameters

- source: Antoine Psat coefficients via the chemicals library; components from the ChemSep databank
- provenance: ideal Raoult-law K-values on the Antoine vapour-pressure basis; Antoine coefficients from the chemicals library (Cory Simon et al.), components from the ChemSep databank

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| phase_identification | ok | 0 | C1@125K ok; C3@300K ok |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — K_i = Psat_i/P is composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0; there is no composition dependence to probe
- `pure_psat_limit` — the row's vapour-pressure basis is the Antoine correlation, not the databank: the measured pure-component bubble at the databank-Psat state deviates +0.45 % (C1, 125 K), -0.06 % (C3, 300 K), +0.63 % (nC4, 280 K) and -0.00 % (CO2, 265 K); the 1e-6 databank-equality limit is the databank-Psat rows' construction and the measured agreement lives in this row's pureK cases instead

## L1/L2 reference-case outcomes

8/8 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `antoine-ideal-k-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `antoine-ideal-k-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `antoine-ideal-k-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `antoine-ideal-k-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml

## References

- Carlson, H. C., Chem. Eng. Prog. 92(10), 35, 1996 (applicability window)
