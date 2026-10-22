# pitzer_nacl_water — Pitzer NaCl(aq) brine (25 C parameter set)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolytePitzerNaCl`.

## Applicability

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/pitzer.yaml
- provenance: Classic 25 C Pitzer NaCl parameter set (PHRQPITZ convention; beta0 0.0765, beta1 0.2664, Cphi 0.00127, Aphi 0.392). Temperature dependence enters only through the carrier Psat — the parameter set is the 25 C one and the osmotic form is T-independent by construction. Molality is clamped to the verified domain (6.15 mol/kg, the saturation anchor). Na2SO4 is out of scope: no component record resolves in the open registry (documented, T-09).

## Literature anchors (spec T-09, tolerance 2 %)

Mean activity coefficients vs Pitzer, Peiper & Busey, J. Phys. Chem. Ref. Data 13(1), 1984, Table A-8 (298.15 K, 1 bar):

| molality (mol/kg) | reference gamma+- | model | deviation |
| --- | --- | --- | --- |
| 0.1 | 0.778 | 0.7785 | -0.06 % |
| 1.0 | 0.657 | 0.6547 | -0.35 % |
| 3.0 | 0.714 | 0.7119 | -0.29 % |

Worst deviation over the full retrieved column (0.1–6 molal): 0.36 % (at 2 mol/kg) — inside the 2 % spec tolerance with wide margin. Supporting outputs at 298.15 K: osmotic coefficient phi(1 mol/kg) = 0.9356; water activity a_w(3 mol/kg) = 0.8932.

Saturation anchor: the solid–liquid equilibrium solve against the published 298.15 K NaCl solubility (6.146 mol/kg at saturated gamma+- 1.0065) lands 6.1548 mol/kg, +0.14 % (spec limit 3 %).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 298.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here — flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## Scope notes

- The mean activity coefficient is obtained from the osmotic form by the exact Gibbs-Duhem integration (the closed forms found in some secondary sources are wrong); the derivation and anchors are pinned by tests/thermo/test_electrolyte.py.
- Precipitating states (molality above the saturation anchor at the flash API boundary) are refused with a typed error rather than silently extrapolated; saturation scans pin their internal split at the fitted saturation molality below the model limit to stay continuous.
- eNRTL and extended-UNIQUAC NaCl rows are registered refusals (see enrtl_nacl_water.md / ext_uniquac_nacl_water.md).

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Pitzer, K. S., Peiper, J. C. & Busey, R. H., "Thermodynamic Properties of Aqueous Sodium Chloride Solutions", J. Phys. Chem. Ref. Data 13(1), 1-102, 1984 (NIST reprint: https://srd.nist.gov/jpcrdreprint/1.555709.pdf)
- Plummer, L. N., Parkhurst, D. L. et al., PHRQPITZ, USGS Water-Resources Investigations Report 88-4153 (parameter convention)
