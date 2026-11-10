# ext_uniquac_nacl_water — Extended UNIQUAC NaCl(aq) brine (Thomsen parameter set)

family `electrolyte` · status **validated** · adapter `ngdesign.amine.electrolyte:ElectrolyteExtUNIQUAC`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/ext_uniquac.yaml
- provenance: Extended UNIQUAC per Thomsen & Rasmussen (1999), Chem. Eng. Sci. 54, 1787-1802 and Thomsen, Rasmussen & Gani (1996), Chem. Eng. Sci. 51, 3675-3683; the r/q/u0/u1 set for Na+-Cl--H2O verified value-for-value against the open-access Leal et al. (2025), Applied Geochemistry 180, 106274 (Tables 1-2), formulation (eqs 15-24, 40-46: psi_ji = exp[(u_ii-u_ji)/T], S_j = sum theta_l psi_lj, infinite-dilution divisor psi_ww = 1, eq 45 unsymmetric molality assembly) read from the same open paper and finite-difference-verified to 6 decimals.  Reaktoro (LGPL-2.1) used as a verification cross-check only, no code copied.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 6.7e-10 | 298.15K/5e+06Pa T_ph 6.7e-10 H 2.9e-10 T_ps 3.9e-10 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Note: literature anchors run in tests/thermo/test_electrolyte.py — mean activity coefficients vs Pitzer, Peiper & Busey 1984 Table A-8 (0.1-6 molal) miss the default 2 % band on six points, worst 4.26 % (1 m, at the characteristic gamma minimum the model reproduces); osmotic coefficients vs Table A-9 miss the band on three points, worst 3.68 % (4 m); the SLE solve gives 6.2358 vs 6.146 mol/kg (+1.5 %).  A few-percent-class fit is the Thomsen-type parameterisation's own published quality.  L0 round trips and the single-liquid limit run today

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

- Thomsen, K. & Rasmussen, P., Chem. Eng. Sci. 54(13), 1787-1802, 1999
- Thomsen, K., Rasmussen, P. & Gani, R., Chem. Eng. Sci. 51(16), 3675-3683, 1996
- Leal, A. M. M., Tambach, T. J., Volpatto, D., Liang, X., Fosbol, P. L. & Thomsen, K., Applied Geochemistry 180, 106274, 2025, doi:10.1016/j.apgeochem.2024.106274, CC BY 4.0 (open-access formulation and parameter verification)
