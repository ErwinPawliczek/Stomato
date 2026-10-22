# pitzer_nacl_water — Pitzer NaCl(aq) brine (25 C parameter set)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolytePitzerNaCl`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/pitzer.yaml
- provenance: Classic 25 C Pitzer NaCl parameter set (PHRQPITZ convention; beta0 0.0765, beta1 0.2664, Cphi 0.00127, Aphi 0.392) validated against Pitzer, Peiper & Busey (1984), J. Phys. Chem. Ref. Data 13(1): mean activity coefficients (Table A-8, 0.1-6 molal within 0.36 %), osmotic coefficients (Table A-9), and the 298.15 K saturation anchor (6.146 mol/kg at gamma 1.0065; the SLE solve lands 6.155, +0.14 %). Water activity a_w = exp(-2 m phi / 55.5084).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 298.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Note: literature anchors run in tests/thermo/test_electrolyte.py — mean activity coefficients from Pitzer, Peiper & Busey 1984 Table A-8 reproduce 0.1-6 molal within 0.36 % (spec points 0.1/1/3 m, tolerance 2 %); osmotic coefficient phi(1 m) = 0.9356 and water activity a_w(3 m) = 0.8932 match the same tables; the solid-liquid saturation solve gives 6.1548 vs 6.146 mol/kg at 298.15 K (+0.14 %, tolerance 3 %). L0 round trips and the single-liquid limit run today

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here -- flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Pitzer, K. S., Peiper, J. C. & Busey, R. H., J. Phys. Chem. Ref. Data 13(1), 1-102, 1984
- Plummer, L. N., Parkhurst, D. L. et al., PHRQPITZ, USGS Water-Resources Investigations Report 88-4153
