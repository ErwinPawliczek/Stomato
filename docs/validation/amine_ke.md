# amine_ke — MDEA Kent-Eisenberg (fixed loading)

family `electrolyte` · status **validated** · adapter `ngdesign.amine.package:AmineKEPackage`.

## Applicability (Carlson 1996)

- component classes: water, amine, acid_gas
- polar: True · electrolyte: True
- T window: 273.15–423.15 K · P window: 100000–8e+06 Pa
- phases: V, L

## Parameters

- source: Kent-Eisenberg model, fixed CO2 loading (0.2 mol/mol MDEA)
- provenance: Kent, R. L. & Eisenberg, B., 'Better Data for Amine Treating', Hydrocarbon Process. 55(2), 87-90, 1976; equilibrium constants and MDEA protonation data as fitted in the ngdesign amine databank; 48.7 wt% MDEA aqueous solvent

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 313.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 313.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 313.15K/5e+06Pa |

Note: validation case ids arrive with T-11..T-13 (loading-isotherm data); L0 round trips and the single-liquid limit run today

Declared exclusions (not silent skips):

- `dhdT_cp` — the reactive-liquid cp is the carrier's databank cp plus the fixed-loading heat of absorption; its T-derivative is not part of the reported cp, so the dH/dT == Cp identity does not apply to this phase
- `gibbs_duhem` — the reactive liquid's ln_phi carries the speciation equilibrium (f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here — flash consistency is pinned by the P1-04 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the reactive liquid (flash consistency y_i P == p_eq_i is pinned by the P1-04 amine tests)
- `pure_psat_limit` — applicability is the aqueous amine liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the amine feed carries reactive acid-gas chemistry)

## L1/L2 reference-case outcomes

13/13 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-323.5K-amine-ke` — coolprop:H2O
- `pure-H2O-420K-amine-ke` — coolprop:H2O
- `pure-H2O-520K-amine-ke` — coolprop:H2O
- `pure-H2O-600K-amine-ke` — coolprop:H2O
- `amine-ke-co2-loading-0.10-313K` — p_CO2 at fixed loading, 4.3638 kmol/m3 (50 wt%) aqueous MDEA at 313.15 K: 0.0093 bara at loading 0.10 and 0.229 bara at loading 0.40 — NeqSim MDEA-model regression anchors (apparent constants fitted to Jou, Mather & Otto, I&EC Process Des. Dev., vol. 21, p. 539, 1982), as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21
- `amine-ke-co2-loading-0.40-313K` — p_CO2 at fixed loading, 4.3638 kmol/m3 (50 wt%) aqueous MDEA at 313.15 K: 0.0093 bara at loading 0.10 and 0.229 bara at loading 0.40 — NeqSim MDEA-model regression anchors (apparent constants fitted to Jou, Mather & Otto, I&EC Process Des. Dev., vol. 21, p. 539, 1982), as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21
- `amine-ke-h2s-loading-0.01-313K` — Jou, Mather & Otto 1982 H2S isotherm, 4.28 kmol/m3 aqueous MDEA at 313.15 K (I&EC Process Des. Dev., vol. 21, p. 539, 1982): p_H2S 0.0108 kPa at loading 0.01, 3.31 kPa at 0.165, 36.9 kPa at 0.453, as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21
- `amine-ke-h2s-loading-0.165-313K` — Jou, Mather & Otto 1982 H2S isotherm, 4.28 kmol/m3 aqueous MDEA at 313.15 K (I&EC Process Des. Dev., vol. 21, p. 539, 1982): p_H2S 0.0108 kPa at loading 0.01, 3.31 kPa at 0.165, 36.9 kPa at 0.453, as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21
- `amine-ke-h2s-loading-0.453-313K` — Jou, Mather & Otto 1982 H2S isotherm, 4.28 kmol/m3 aqueous MDEA at 313.15 K (I&EC Process Des. Dev., vol. 21, p. 539, 1982): p_H2S 0.0108 kPa at loading 0.01, 3.31 kPa at 0.165, 36.9 kPa at 0.453, as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21

## References

- Kent, R. L. & Eisenberg, B., Hydrocarbon Process. 55(2), 87-90, 1976
- Jou, F.-Y. et al., 'Equilibrium Partial Pressures of CO2 and H2S in Aqueous MDEA Solutions', Can. J. Chem. Eng. 71, 264-268, 1993
