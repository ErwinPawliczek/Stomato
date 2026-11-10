# pitzer_debye_huckel — Pitzer-Debye-Hückel

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolytePDH`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/enrtl.yaml (aphi, rho only)
- provenance: The long-range term of enrtl_nacl_water with no short-range binary, A_phi = 0.392, rho = 14.9 (Pitzer 1980; Chen et al. 1982). No fitted parameters.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 5.2e-09 | 298.15K/5e+06Pa T_ph 5.2e-09 H 2.7e-09 T_ps 1.8e-10 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat), not a Gibbs-excess composition derivative; flash consistency is pinned by tests/thermo/test_electrolyte_variants.py instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency is pinned by tests/thermo/test_electrolyte_variants.py)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

8/8 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-293.15K-electrolyte` — coolprop:H2O
- `pure-H2O-298.15K-electrolyte` — coolprop:H2O
- `pure-H2O-303.15K-electrolyte` — coolprop:H2O
- `nacl-cg85-vp-298.15K-0.1m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 0.100 row: 3.15809 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04
- `nacl-cg85-vp-298.15K-0.2m` — Clarke, E. C. W. & Glew, D. N., 'Evaluation of the thermodynamic functions for aqueous sodium chloride from equilibrium and calorimetric measurements below 154 C', J. Phys. Chem. Ref. Data 14(2), 489-610, 1985, doi:10.1063/1.555730, Table 21 A (water saturation vapour pressure of sodium chloride solution, kPa), printed p. 537, 25.000 C column, molality 0.200 row: 3.14768 kPa; read from the NIST reprint https://srd.nist.gov/jpcrdreprint/1.555730.pdf, page image checked, retrieved 2026-11-04

## References

- Pitzer, K. S., J. Am. Chem. Soc. 102(9), 2902-2906, 1980
- Chen, C.-C., Britt, H. I., Boston, J. F. & Evans, L. B., AIChE J. 28(4), 588-596, 1982
- Pitzer, K. S., Peiper, J. C. & Busey, R. H., J. Phys. Chem. Ref. Data 13(1), 1-102, 1984
