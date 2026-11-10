# iapws_if97 — IAPWS-IF97 industrial water and steam

family `helmholtz` · status **validated** · adapter `ngdesign.thermo.helmholtz:IAPWSPackage`.

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

Note: IF97 backend exposes no fugacity coefficients (CoolProp 8), so Phase.ln_phi stays empty for this row; phase_props and flashes carry full properties. The T-15 saturated-phase label swap no longer reproduces: re-measured 2026-11-04, the three h2o-if97 cases pass every property (e.g. rho_V 0.235059 vs 0.235067 at 347.39 K), so their stale assessed notes were removed.

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure water only - no binary composition path to integrate over

## L1/L2 reference-case outcomes

31/31 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `h2o-if97-273.179K` — coolprop:Water (CoolProp 8.0.0 HEOS reference values; state points match the hand-typed NIST WebBook h2o-nist cases)
- `h2o-if97-347.390K` — coolprop:Water (CoolProp 8.0.0 HEOS reference values; state points match the hand-typed NIST WebBook h2o-nist cases)
- `h2o-if97-401.605K` — coolprop:Water (CoolProp 8.0.0 HEOS reference values; state points match the hand-typed NIST WebBook h2o-nist cases)
- `asme-steam-r1-300K-3MPa` — IAPWS R7-97(2012), Table 5 (Region 1 check values): T=300 K, p=3 MPa, v=0.100215168e-2 m3/kg, cp=0.417301218e1 kJ/(kg K); retrieved 2026-10-23 (density cross-checked against the shared kernel in-session before binding)
- `asme-steam-psat-300K` — IAPWS R7-97(2012), Table 35 (Region 4 saturation line): Psat(300 K) = 0.353658941e-2 MPa; retrieved 2026-10-23
- `if97-r7-r1-300K-80MPa` — IAPWS R7-97(2012), Revised Release on the IAPWS Industrial Formulation 1997, Table 5 (Region 1 check values), T = 300 K, p = 80 MPa: v = 0.971180894e-3 m3/kg, cp = 0.401008987e1 kJ/(kg K); https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04
- `if97-r7-r1-500K-3MPa` — IAPWS R7-97(2012), Table 5 (Region 1 check values), T = 500 K, p = 3 MPa: v = 0.120241800e-2 m3/kg, cp = 0.465580682e1 kJ/(kg K); https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04
- `if97-r7-r2-300K-3.5kPa` — IAPWS R7-97(2012), Table 15 (Region 2 check values), T = 300 K, p = 0.0035 MPa: v = 0.394913866e2 m3/kg, cp = 0.191300162e1 kJ/(kg K); https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04
- `if97-r7-r2-700K-30MPa` — IAPWS R7-97(2012), Table 15 (Region 2 check values), T = 700 K, p = 30 MPa: v = 0.542946619e-2 m3/kg, cp = 0.103505092e2 kJ/(kg K); https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04
- `if97-r7-psat-500K` — IAPWS R7-97(2012), Table 35 (Region 4 saturation pressures), T = 500 K: p_s = 0.263889776e1 MPa; https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04
- `if97-r7-psat-600K` — IAPWS R7-97(2012), Table 35 (Region 4 saturation pressures), T = 600 K: p_s = 0.123443146e2 MPa; https://iapws.org/technical-guidance/release/IF97-Rev.download, retrieved 2026-11-04

## References

- Wagner, W., Cooper, J. R., Dittmann, A., et al., 'The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam', J. Eng. Gas Turbines Power 122, 150-182, 2000 (CoolProp IF97::Water backend)
- CoolProp 8.0.0 IF97 backend, Psat(373.15 K) = 101417.978 Pa in-session (vs 101417.997 Pa for IAPWS-95)
