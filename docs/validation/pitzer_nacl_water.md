# pitzer_nacl_water — Pitzer single-salt brine (NaCl, KCl, KBr, LiCl, NaBr, MgCl2; 25 C PHRQPITZ sets)

family `electrolyte` · status **validated** · adapter `ngdesign.amine.electrolyte:ElectrolytePitzerNaCl`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/pitzer.yaml
- provenance: Single-salt Pitzer sets at 25 C keyed by salt and ion pair, all from the PHRQPITZ data base as printed in USGS WRI 88-4153 (Plummer, Parkhurst, Fleming & Dunkle 1988, doi:10.3133/wri884153) Attachment C.6, pp. 190-192 (U.S. Government work; per-value primary references in the params file: Harvie, Moller & Weare 1984 for NaCl, KCl, MgCl2; Pitzer & Mayorga 1973 for KBr, LiCl, NaBr). Aphi 0.392, b 1.2, alpha 2.0. NaCl (beta0 0.0765, beta1 0.2664, Cphi 0.00127) validated against Pitzer, Peiper & Busey (1984), J. Phys. Chem. Ref. Data 13(1): mean activity coefficients (Table A-8, 0.1-6 molal within 0.36 %), osmotic coefficients (Table A-9), and the 298.15 K saturation anchor (6.146 mol/kg at gamma 1.0065; the SLE solve lands 6.155, +0.14 %). KCl/KBr/LiCl/NaBr validated against Hamer & Wu (1972), J. Phys. Chem. Ref. Data 1, 1047 (phi within 0.6 %, gamma within 0.9 % to each salt's cap); MgCl2 against Goldberg & Nuttall (1978), J. Phys. Chem. Ref. Data 7, 263, Table 17 (a_w within 0.2 %, phi within 1.9 %, gamma 1.2-3.2 % low, assessed). Water activity a_w = exp(-nu m phi / 55.5084).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 6.7e-10 | 298.15K/5e+06Pa T_ph 6.7e-10 H 2.9e-10 T_ps 3.9e-10 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Note: literature anchors run in tests/thermo/test_electrolyte.py — mean activity coefficients from Pitzer, Peiper & Busey 1984 Table A-8 reproduce 0.1-6 molal within 0.36 % (spec points 0.1/1/3 m, tolerance 2 %); osmotic coefficient phi(1 m) = 0.9356 and water activity a_w(3 m) = 0.8932 match the same tables; the solid-liquid saturation solve gives 6.1548 vs 6.146 mol/kg at 298.15 K (+0.14 %, tolerance 3 %). The other salts' anchors (Hamer & Wu 1972 Tables 9/17/28/29; Goldberg & Nuttall 1978 Table 17) and the per-salt flash surface run in tests/thermo/test_electrolyte_salts.py. L0 round trips and the single-liquid limit run today (on NaCl)

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here -- flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

16/16 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-293.15K-electrolyte` — coolprop:H2O
- `pure-H2O-298.15K-electrolyte` — coolprop:H2O
- `pure-H2O-303.15K-electrolyte` — coolprop:H2O
- `nacl-cg85-vp-298.15K-0.1m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 0.100 row: 3.15809 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-0.2m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 0.200 row: 3.14768 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-1.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 1.000 row: 3.06336 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-2.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 2.000 row: 2.95097 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-4.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 4.000 row: 2.69667 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-6.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 6.000 row: 2.40772 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-293.15K-4.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 536, 20.000 C column, molality 4.000 row: 1.99159 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-293.15K-6.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 536, 20.000 C column, molality 6.000 row: 1.77774 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-303.15K-4.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 30.000 C column, molality 4.000 row: 3.61069 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-303.15K-6.0m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 30.000 C column, molality 6.000 row: 3.22487 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04

## References

- Pitzer, K. S., Peiper, J. C. & Busey, R. H., J. Phys. Chem. Ref. Data 13(1), 1-102, 1984
- Plummer, L. N., Parkhurst, D. L., Fleming, G. W. & Dunkle, S. A., PHRQPITZ, USGS Water-Resources Investigations Report 88-4153, 1988, doi:10.3133/wri884153 (Attachment C.6)
- Harvie, C. E., Moller, N. & Weare, J. H., Geochim. Cosmochim. Acta 48, 723-751, 1984
- Pitzer, K. S. & Mayorga, G., J. Phys. Chem. 77, 2300-2308, 1973
- Hamer, W. J. & Wu, Y.-C., J. Phys. Chem. Ref. Data 1, 1047-1100, 1972, doi:10.1063/1.3253108
- Goldberg, R. N. & Nuttall, R. L., J. Phys. Chem. Ref. Data 7, 263-310, 1978, doi:10.1063/1.555569
