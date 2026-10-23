# asme_steam — ASME steam tables (IAPWS-IF97 basis, ASME-labelled)

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.helmholtz:ASMESteamPackage`.

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

Note: Same kernel as iapws_if97; the checks and their results are identical by construction.

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure water only - no binary composition path to integrate over

## L1/L2 reference-case outcomes

4/4 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `asme-steam-r1-300K-3MPa` — IAPWS R7-97(2012), Table 5 (Region 1 check values): T=300 K, p=3 MPa, v=0.100215168e-2 m3/kg, cp=0.417301218e1 kJ/(kg K); retrieved 2026-10-23 (density cross-checked against the shared kernel in-session before binding)
- `asme-steam-psat-300K` — IAPWS R7-97(2012), Table 35 (Region 4 saturation line): Psat(300 K) = 0.353658941e-2 MPa; retrieved 2026-10-23

## References

- ASME, 'ASME Steam Tables', 7th ed., 2000 (computed from IAPWS-IF97; this row is that kernel under the ASME label)
- IAPWS, 'Revised Release on the IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam', R7-97(2012) - Table 5 (Region 1) and Table 35 (Region 4 saturation line) check values bound as cases; retrieved 2026-10-23
