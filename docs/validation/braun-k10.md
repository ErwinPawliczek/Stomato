# braun-k10 — Braun K10 low-pressure limit (ideal-K asymptote of the K10 charts)

family `kvalue` · status **provisional** · adapter `ngdesign.thermo.kvalue:BraunK10Thermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon
- polar: False · electrolyte: False
- T window: 200–560 K · P window: 1000–700000 Pa
- phases: V, L, VLL

## Parameters

- source: vapour pressures from the ChemSep databank Psat basis; the row refuses service above 0.7 MPa by construction
- provenance: Braun convergence-pressure K10 charts, Cajander, B. C., Hipkin, H. G. & Lenoir, J. M., 'Prediction of Equilibrium Ratios from Nomographs of Improved Accuracy', J. Chem. Eng. Data 5(3), 251-259, 1960; the digitised polynomial fits are blocked on a published parameter source (GitHub issue 139), so the row implements the charts' documented low-pressure asymptote K_i = Psat_i/P and refuses outside it (deviation recorded for the T-05 review)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 2.2e-16 | C1@125K bubble 0 dew 0; nC4@280K bubble 2.2e-16 dew 0 |
| phase_identification | ok | 0 | C1@125K ok; nC4@280K ok |
| round_trip | ok | 0 | 300K/100000Pa T_ph 0 H 0 T_ps 0 |
| dhdT_cp | ok | 1.7e-07 | 300K/100000Pa vapor cp 55.0789 dH/dT 55.0789 |
| single_liquid_limit | ok | 0 | 300K/160000Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/100000Pa |

Note: the declared pure_psat_limit/phase_identification points stay inside the 0.7 MPa service cap (C1 and nC4); the propane/CO2 saturation points above the cap are refused by construction and covered by the applicability window instead

Declared exclusions (not silent skips):

- `gibbs_duhem` — the Braun K10 asymptote K10_i(T, P) is composition-independent: the Gibbs-Duhem residual is identically zero by construction and the check's |sum x dlnphi| / sum |x dlnphi| normalisation degenerates to 0/0

## L1/L2 reference-case outcomes

4/4 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `braun-k10-pureK-C1-125K` — coolprop:CH4 - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml
- `braun-k10-pureK-nC4-280K` — coolprop:n-Butane - K = Psat/P at P = Psat is the definitional pure-component saturation limit (catalogue plan L0); the case pressure is the CoolProp saturation pressure regenerated in data/validation/cases.yaml

## References

- Cajander, B. C., Hipkin, H. G. & Lenoir, J. M., J. Chem. Eng. Data 5(3), 251-259, 1960
