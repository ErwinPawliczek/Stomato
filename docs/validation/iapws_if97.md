# iapws_if97 — IAPWS-IF97 industrial water and steam

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.helmholtz:IAPWSPackage`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: False
- T window: 273.15–1073.15 K · P window: 500–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@373.15K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@300K ok; H2O@400K ok |
| round_trip | ok | 2e-13 | 350K/200000Pa T_ph 4.3e-14 H 2e-13 T_ps 4.3e-14; 400K/300000Pa T_ph 2.5e-14 H 8.1e-14 T_ps 2.5e-14 |
| dhdT_cp | ok | 1.1e-07 | 500K/100000Pa vapor cp 35.6917 dH/dT 35.6917 |
| single_liquid_limit | ok | 0 | 300K/100000Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/200000Pa |

Note: IF97 backend exposes no fugacity coefficients (CoolProp 8), so Phase.ln_phi stays empty for this row; phase_props and flashes carry full properties.

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure water only - no binary composition path to integrate over

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Wagner, W., Cooper, J. R., Dittmann, A., et al., 'The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam', J. Eng. Gas Turbines Power 122, 150-182, 2000 (CoolProp IF97::Water backend)
- CoolProp 8.0.0 IF97 backend, Psat(373.15 K) = 101417.978 Pa in-session (vs 101417.997 Pa for IAPWS-95)
