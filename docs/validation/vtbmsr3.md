# vtbmsr3 — VTBMSR-III RKS with polar alpha and T-dependent translation (Mangold 2019), density only

family `special` · status **provisional** · adapter `ngdesign.thermo.vtbmsr:VtbmsrPackage`.

## Applicability (Carlson 1996)

- component classes: water, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 620.5–657 K · P window: 2.7e+07–2.639e+08 Pa
- phases: V

## Parameters

- source: data/thermo_params/vtbmsr/mangold2019.yaml
- provenance: Mangold, Pilz, Bjelic & Vogel, J. Supercrit. Fluids 153 (2019) 104476: Table 2 (Tc, pc, omega), Table 5 (c0-c2, p0-p2; water column H2O(v/sc) set 3), Table 7 (k_b,ij sets 2; k_a and l unused). Read from the open full text 2026-11-09.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| determinism | ok | 0 | two instances bit-identical at 642K/1.02e+08Pa |

Note: The declared check exercises the one surface the adapter offers (PT flash determinism on a bound T3 state); every excluded check needs a surface the density-only scope does not provide, each refused with the typed VtbmsrError.

Declared exclusions (not silent skips):

- `dhdT_cp` — density-only adapter - enthalpy and cp are not computed (NaN)
- `gibbs_duhem` — no fugacity coefficients - ln phi is not part of the density-only surface
- `phase_identification` — the check anchors on the package's own bubble pressure, which the density-only adapter refuses (no validated phase equilibrium)
- `pure_psat_limit` — density-only adapter - pure_psat returns None (no vapour-pressure model is validated)
- `round_trip` — the check iterates flash_ph/flash_ps, which the density-only adapter refuses (enthalpy and entropy are not computed)
- `single_liquid_limit` — the adapter answers single-phase supercritical states only and refuses liquid-phase requests

### L4 cross-model pairs

- n/a — refuses the slice feed: VtbmsrError: VTBMSR-III adapter has no validated phase equilibrium: no dew point

## L1/L2 reference-case outcomes

9/9 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `h2o-air-620.5K-27MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-638.5K-44MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-640K-68.3MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-642K-102MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-645.5K-152.9MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-650K-195.3MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-652K-214.8MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-653.5K-231.5MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04
- `h2o-air-657K-263.9MPa` — Japas & Franck [30] experimental molar volume as printed in Mangold et al. 2019 Table 8 (doi:10.1016/j.supflu.2019.02.016, open); composition x_O2/x_N2 = 1/4 assumed by Mangold (not specified in Japas & Franck); density = printed molar volume converted with NIST molar masses (see pack header); retrieved 2026-11-04

## References

- Mangold, F., Pilz, St., Bjelic, S., Vogel, F., 'Equation of state and thermodynamic properties for mixtures of H2O, O2, N2, and CO2 from ambient up to 1000 K and 280 MPa', J. Supercrit. Fluids 153 (2019) 104476, doi:10.1016/j.supflu.2019.02.016 (CC BY 4.0)
- Kay, W. B., 'Density of hydrocarbon gases and vapors at high temperature and pressure', Ind. Eng. Chem. 28 (1936) 1014 (pseudo-critical temperature scope guard)
