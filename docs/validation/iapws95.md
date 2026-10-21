# iapws95 — IAPWS-95 water and steam

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.helmholtz:IAPWSPackage`.

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

25/25 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `h2o-nist-273.179K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-347.390K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-401.605K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-500.184K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-600.070K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21

## References

- Wagner, W., Cooper, J. R., Dittmann, A., et al., 'The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam', J. Eng. Gas Turbines Power 122, 150-182, 2000 (IAPWS-95 revised release, 2016; CoolProp HEOS::Water implements the IAPWS-95 formulation)
- CoolProp 8.0.0 HEOS water backend, verified in-session against thermo 0.6.1 IAPWS-95 (density agreement ~1e-11 relative at 300 K, 1 bar) and IAPWS saturation tables (Psat(373.15 K) = 101417.997 Pa)
