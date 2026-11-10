# iapws95 — IAPWS-95 water and steam

family `helmholtz` · status **validated** · adapter `ngdesign.thermo.helmholtz:IAPWSPackage`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: False
- T window: 251.165–1273 K · P window: 500–1e+09 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@373.15K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@300K ok; H2O@400K ok |
| round_trip | ok | 2.4e-13 | 350K/200000Pa T_ph 4e-14 H 2.4e-13 T_ps 4e-14; 400K/300000Pa T_ph 5.4e-14 H 1.6e-13 T_ps 5.4e-14 |
| dhdT_cp | ok | 1.1e-07 | 500K/100000Pa vapor cp 35.6929 dH/dT 35.6929 |
| single_liquid_limit | ok | 0 | 300K/100000Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/200000Pa |

Note: Pure-water adapter; the liquid root reports as AQUEOUS. CoolProp is imported lazily; without the optional coolprop extra the row loads but every evaluation raises CoolPropUnavailable.

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure water only - no binary composition path to integrate over

## L1/L2 reference-case outcomes

40/40 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `h2o-nist-273.179K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-347.390K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-401.605K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-500.184K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-600.070K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `iapws95-r6-sat-275K` — IAPWS R6-95(2018), Revised Release on the IAPWS Formulation 1995 for the Thermodynamic Properties of Ordinary Water Substance, Table 8 (two-phase verification values), T = 275 K: p_sigma = 0.698451167e-3 MPa, rho' = 0.999887406e3, rho'' = 0.550664919e-2 kg/m3; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04
- `iapws95-r6-sat-450K` — IAPWS R6-95(2018), Table 8 (two-phase verification values), T = 450 K: p_sigma = 0.932203564 MPa, rho' = 0.890341250e3, rho'' = 0.481200360e1 kg/m3; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04
- `iapws95-r6-sat-625K` — IAPWS R6-95(2018), Table 8 (two-phase verification values), T = 625 K: p_sigma = 0.169082693e2 MPa, rho' = 0.567090385e3, rho'' = 0.118290280e3 kg/m3; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04
- `iapws95-r6-1phase-300K-20MPa` — IAPWS R6-95(2018), Table 7 (single-phase verification values), T = 300 K, rho = 0.1005308e4 kg/m3, p = 0.200022515e2 MPa; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04
- `iapws95-r6-1phase-500K-1MPa` — IAPWS R6-95(2018), Table 7 (single-phase verification values), T = 500 K, rho = 0.4532e1 kg/m3, p = 0.999938125 MPa; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04
- `iapws95-r6-1phase-900K-20MPa` — IAPWS R6-95(2018), Table 7 (single-phase verification values), T = 900 K, rho = 0.526150e2 kg/m3, p = 0.200000690e2 MPa; https://iapws.org/technical-guidance/release/IAPWS-95.download, retrieved 2026-11-04

## References

- Wagner, W., Cooper, J. R., Dittmann, A., et al., 'The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam', J. Eng. Gas Turbines Power 122, 150-182, 2000 (IAPWS-95 revised release, 2016; CoolProp HEOS::Water implements the IAPWS-95 formulation)
- CoolProp 8.0.0 HEOS water backend, verified in-session against thermo 0.6.1 IAPWS-95 (density agreement ~1e-11 relative at 300 K, 1 bar) and IAPWS saturation tables (Psat(373.15 K) = 101417.997 Pa)
