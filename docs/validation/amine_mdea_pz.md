# amine_mdea_pz — Mixed amines (MDEA+PZ)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.package:AmineMdeaPzPackage`.

## Applicability (Carlson 1996)

- component classes: water, amine, acid_gas
- polar: True · electrolyte: True
- T window: 298.15–343.15 K · P window: 100000–8e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/amine/mdea_pz.yaml
- provenance: Bishnoi 2000, Tables 5.4b and 5.5, mole-fraction equilibrium constants for the MDEA + PZ + CO2 reaction set, applied with unit activity coefficients where the source regressed them on electrolyte-NRTL. Against the source's own Table 5.7 (0.6 M PZ, 4 M MDEA) the pressure is 0.23 to 2.7 times the measurement, rms ln p about 0.7, so the row is a screening model. CO2 only, H2S refuses.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 313.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 1.2e-11 | 313.15K/5e+06Pa T_ph 1.2e-11 H 7.5e-12 T_ps 3e-13 |
| determinism | ok | 0 | two instances bit-identical at 313.15K/5e+06Pa |

Note: validation case ids arrive with T-11..T-13 (loading-isotherm data); L0 round trips and the single-liquid limit run today

Declared exclusions (not silent skips):

- `dhdT_cp` — the reactive-liquid cp is the carrier's databank cp plus the fixed-loading heat of absorption; its T-derivative is not part of the reported cp, so the dH/dT == Cp identity does not apply to this phase
- `gibbs_duhem` — the reactive liquid's ln_phi carries the speciation equilibrium (f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here — flash consistency is pinned by the P1-04 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the reactive liquid (flash consistency y_i P == p_eq_i is pinned by the P1-04 amine tests)
- `pure_psat_limit` — applicability is the aqueous amine liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the amine feed carries reactive acid-gas chemistry)

## L1/L2 reference-case outcomes

8/8 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-293.15K-electrolyte` — coolprop:H2O
- `pure-H2O-298.15K-electrolyte` — coolprop:H2O
- `pure-H2O-303.15K-electrolyte` — coolprop:H2O
- `pure-H2O-353.15K-electrolyte` — coolprop:H2O

## References

- Bishnoi, S., PhD dissertation, University of Texas at Austin, 2000
- Bishnoi, S. & Rochelle, G. T., AIChE J. 48(12), 2788-2799, 2002
