# sour_water — Sour water (EPA-600/2-80-067 SWEQ, NH3-H2S-H2O)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolyteSourWater`.

## Applicability (Carlson 1996)

- component classes: water, acid_gas
- polar: True · electrolyte: True
- T window: 293.15–373.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/reactions.yaml
- provenance: Wilson, G. M., 'Sour Water Equilibria', EPA-600/2-80-067 (1980): NH3-H2S-H2O speciation with the report's reaction polynomials (k3 association, k5/k6/k7 dissociation; ln k = A + B/T + C/T^2 + D/T^3 + E/T^4, T in degR, concentrations gmol/kg solution) and Henry correlations (psia per gmol/kg solution).  Constants character-verified against the report's printed worked examples (printed pp. 52-53) and cross-checked against DWSIM's transcription; the k5 D-coefficient keeps the report's 2.5551e11 (DWSIM carries 2.555e11, a dropped digit, -3.4 % on k5 at 100 C -- see docs/validation.md).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 311.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 311.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 311.15K/5e+06Pa |

Note: literature anchors run in tests/thermo/test_electrolyte.py — the six printed constants and both Henry correlations match the report's worked examples; H2S partial pressures over the pH-7.00 buffered 0.010-m solution vs Table 21 (API column): 59.33/60.14/61.83/68.80 mmHg at 80/100/120/140 C vs 59.3/60.1/61.8/68.0 (+0.1 %, +0.1 %, +0.1 %, +1.2 %; tolerance 10 %); the spec's 90 C point uses the linearly interpolated API anchor 59.70 mmHg (the table has no 90 C row) against the model's 59.89 mmHg, +0.32 %. Known applicability limit — EPA Table 19 (Terres) 28 C rows deviate up to +230 % on H2S while the 40 C rows reproduce within +15.7 % NH3 / +8.1 % H2S; the report's own VK and API calculated columns disagree by up to 65 % on the same rows and applying the report's ionic-strength correction to k5 over-corrects (-90 %), so the scatter is a declared limit of this implementation — rely on 40-100 C (the anchors below 40 C are the weak ones). L0 round trips and the single-liquid limit run today

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here -- flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Wilson, G. M., 'Sour Water Equilibria', EPA-600/2-80-067, 1980
- Shih, T. S. et al., H2S solubility in buffered aqueous solutions (as tabulated in EPA-600/2-80-067, Table 21)
- Edwards, T. J. et al. 1978 (the report's API comparison column)
