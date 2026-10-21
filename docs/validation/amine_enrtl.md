# amine_enrtl — MDEA Kent-Eisenberg + electrolyte-NRTL (fixed loading)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.package:AmineENRTLPackage`.

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

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Kent, R. L. & Eisenberg, B., Hydrocarbon Process. 55(2), 87-90, 1976
- Jou, F.-Y. et al., 'Equilibrium Partial Pressures of CO2 and H2S in Aqueous MDEA Solutions', Can. J. Chem. Eng. 71, 264-268, 1993
