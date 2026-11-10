# enrtl_rk — ENRTL with Redlich-Kwong vapour

family `electrolyte` · status **validated** · adapter `ngdesign.amine.electrolyte:ElectrolyteENRTLRK`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/enrtl.yaml (liquid); the rk row for the vapour
- provenance: The liquid is enrtl_nacl_water unchanged. The vapour is the catalogue's rk row (RKMIX, ChemSep critical constants), which supplies phi_V, density, enthalpy and entropy. Real-vapour water K-value: K_H2O = a_w Psat (phi_sat / phi_V) / P, Poynting term of the brine omitted. At 293-303 K the effect is of order 1e-4 on the bubble pressure, because water's Psat is small; the row exists for the vapour's fugacity and properties, not for a large VLE shift.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 6.7e-10 | 298.15K/5e+06Pa T_ph 6.7e-10 H 2.9e-10 T_ps 3.9e-10 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat), not a Gibbs-excess composition derivative; flash consistency is pinned by tests/thermo/test_electrolyte_variants.py instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency is pinned by tests/thermo/test_electrolyte_variants.py)
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

- Chen, C.-C., Britt, H. I., Boston, J. F. & Evans, L. B., AIChE J. 28(4), 588-596, 1982
- Chen, C.-C. & Evans, L. B., AIChE J. 32(3), 444-454, 1986
- Redlich, O. & Kwong, J. N. S., Chem. Rev. 44(1), 233-244, 1949
