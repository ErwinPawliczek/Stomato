# ideal-lk — Ideal K-values with the Lee-Kesler departure enthalpy basis

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:IdealRaoultThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water, alcohol, polar_organic
- polar: True · electrolyte: False
- T window: 90–620 K · P window: 1000–3e+06 Pa
- phases: V, L, VLL

## Parameters

- source: vapour pressures from the ChemSep databank Psat basis
- provenance: shares the ideal-raoult adapter and databank Psat basis; the row's named role is the Lee-Kesler departure enthalpy basis (the row options declare enthalpy lee_kesler), which is the KValuePackage implementation for every row of this family

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; C3@300K bubble 0 dew 1.2e-16; nC4@280K bubble 2.2e-16 dew 0; CO2@265K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; C3@300K ok |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| single_liquid_limit | ok | 0 | 300K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the row shares the ideal-raoult adapter (databank Psat, K_i = Psat_i/P); the lee_kesler enthalpy declaration names the departure basis the plan assigns this row

Declared exclusions (not silent skips):

- `gibbs_duhem` — K_i = Psat_i/P is composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0; there is no composition dependence to probe

## L1/L2 reference-case outcomes

8/8 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ideal-lk-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-C3-300K` — coolprop:Propane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `ideal-lk-pureK-CO2-265K` — coolprop:CO2 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml

## References

- Raoult, F.-M., Compt. Rend. 104, 1430-1433, 1887
- Lee, B. I. & Kesler, M. G., AIChE J. 21(3), 510-527, 1975 (departure basis)
