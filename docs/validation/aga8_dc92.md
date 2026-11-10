# aga8_dc92 — AGA 8 DC92 detail equation of state (gas phase)

family `helmholtz` · status **validated** · adapter `ngdesign.thermo.aga8:Aga8Dc92Package`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 143.15–676.48 K · P window: 100000–2.8e+08 Pa
- phases: V

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| determinism | ok | 0 | two instances bit-identical at 350K/5e+06Pa |
| dhdT_cp | ok | 5.6e-07 | 350K/5e+06Pa vapor cp 41.0134 dH/dT 41.0134 |

Note: The declared checks exercise the gas surface the adapter offers (PT flash determinism, cp self-consistency); every excluded check exercises an operation the DC92 method structurally cannot provide, each refused with the typed Aga8Dc92Error.

Declared exclusions (not silent skips):

- `gibbs_duhem` — no fugacity coefficients - ln phi is not part of the DC92 surface
- `phase_identification` — the check anchors on the databank Psat, which pure_psat returns None for (no vapour-pressure correlation in the DC92 method)
- `pure_psat_limit` — gas-only method - no vapour-pressure correlation exists in DC92
- `round_trip` — the check iterates flash_ph/flash_ps, which the gas-only adapter refuses by design (no H/S-driven flashes are offered)
- `single_liquid_limit` — gas-only method - the adapter refuses liquid-phase requests

### L4 cross-model pairs

- n/a — refuses the slice feed: Aga8Dc92Error: AGA8 DC92 models gas only: no dew point

## L1/L2 reference-case outcomes

12/12 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `aga8-dc92-nist-check-gas-400K-50MPa` — Lemmon, Bell, Heinemann & Lu (2017) AGA8 Version 2.0 [Software], NIST, github.com/usnistgov/AGA8 @ 3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce, AGA8CODE/C Detail_test_01.cpp printed check values: 21-component example gas at 400 K / 50 000 kPa - molar density 12.80792403648801 mol/l, molar mass 20.54333051 g/mol, Z 1.173801364147326, cp 58.54617672380667 J/(mol K); retrieved 2026-10-21
- `aga8-n2-density-249.959K-5.024MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 0 (nitrogen mass density), T = 249.959 K, p = 5024.18 kPa, rho = 69.90185 kg/m3; retrieved 2026-11-04
- `aga8-n2-density-299.972K-10.974MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 0 (nitrogen mass density), T = 299.972 K, p = 10974.4 kPa, rho = 122.2529 kg/m3; retrieved 2026-11-04
- `aga8-n2-density-399.99K-17.250MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 0 (nitrogen mass density), T = 399.99 K, p = 17249.6 kPa, rho = 135.0429 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.79998-249.914K-5.016MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.79998, T = 249.914 K, p = 5015.83 kPa, rho = 51.0598 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.79998-299.909K-10.001MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.79998, T = 299.909 K, p = 10001.4 kPa, rho = 82.4925 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.89984-240.008K-10.029MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.89984, T = 240.008 K, p = 10028.6 kPa, rho = 127.633 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.89984-299.999K-10.050MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.89984, T = 299.999 K, p = 10050.0 kPa, rho = 79.2704 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.89984-350.001K-19.983MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.89984, T = 350.001 K, p = 19983.2 kPa, rho = 125.244 kg/m3; retrieved 2026-11-04
- `aga8-c1n2-x0.89984-400.005K-19.369MPa` — Chamorro, C. R., Segovia, J. J., Martin, M. C., Villamanan, M. A., Estela-Uribe, J. F., Trusler, J. P. M., 'Measurement of the (pressure, density, temperature) relation of two (methane + nitrogen) gas mixtures at temperatures between 240 and 400 K and pressures up to 20 MPa using an accurate single-sinker densimeter', J. Chem. Thermodyn. 38, 916-922, 2006, doi:10.1016/j.jct.2005.10.004; NIST TRC ThermoML record https://trc.nist.gov/ThermoML/10.1016/j.jct.2005.10.004.xml, PureOrMixtureData dataset 1 (mass density), x_CH4 = 0.89984, T = 400.005 K, p = 19369.0 kPa, rho = 101.162 kg/m3; retrieved 2026-11-04

## References

- Starling, K. E., Savidge, J. L., 'Compressibility Factors of Natural Gas and Other Related Hydrocarbon Gases', AGA Transmission Measurement Committee Report No. 8, 2nd ed., 1992 (coefficients as published in NIST''s public-domain reference implementation, github.com/usnistgov/AGA8 @ 3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce, AGA8CODE/C, retrieved 2026-10; the port reproduces Detail_test_01.cpp check values)
