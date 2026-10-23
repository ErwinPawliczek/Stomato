# enrtl_nacl_water — eNRTL NaCl(aq) brine (25 C parameter set)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolyteENRTLNaCl`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/enrtl.yaml
- provenance: eNRTL NaCl-H2O binary per Chen & Evans (1986), AIChE J. 32(3), 444-454 (tau_CA,w -4.5916, tau_w,CA 9.0234, alpha 0.2; transcribed from the open-access Kwaterski & Herri copy) with the Pitzer-Debye-Hueckel mole-fraction long-range term per Chen, Britt, Boston & Evans (1982), AIChE J. 28(4), 588-596 (A_phi 0.392, rho 14.9).  Salt-side composition derivatives are numeric central differences of n*G^E/RT; the unsymmetric molality-scale conversion (ln gamma+-(m) = ln gamma+-(x) - ln(1 + nu m M_w)) and a_w = gamma_w x_w follow Chen (1982).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 298.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Note: literature anchors run in tests/thermo/test_electrolyte.py — mean activity coefficients vs Pitzer, Peiper & Busey 1984 Table A-8 (0.1-6 molal) miss the default 2 % band on four points, worst 4.99 % (6 m; the model's own published fit quality is ~1-5 %, sigma_phi 1.18 % per Kwaterski & Herri); osmotic coefficients vs Table A-9 miss the band once (6 m, -2.84 %); the SLE solve gives 6.8905 vs 6.146 mol/kg (+12.2 %, the flat gamma curve past the minimum). L0 round trips and the single-liquid limit run today

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here -- flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Chen, C.-C. & Evans, L. B., AIChE J. 32(3), 444-454, 1986
- Chen, C.-C., Britt, H. I., Boston, J. F. & Evans, L. B., AIChE J. 28(4), 588-596, 1982
- Kwaterski, M. & Herri, J.-M. (open-access copy carrying the printed Chen & Evans NaCl tau table)
