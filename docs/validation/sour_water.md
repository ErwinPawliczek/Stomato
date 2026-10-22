# sour_water — Sour water (EPA-600/2-80-067 SWEQ, NH3-H2S-H2O)

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolyteSourWater`.

## Applicability

- component classes: water, acid_gas
- polar: True · electrolyte: True
- T window: 293.15–373.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/reactions.yaml
- provenance: Wilson sour-water equilibrium model, EPA-600/2-80-067 (1980). Reaction constants (k3 association, k5/k6/k7 dissociation; ln k = A + B/T + C/T^2 + D/T^3 + E/T^4, T in Rankine, concentrations gmol/kg solution) and Henry polynomials transcribed from the report's worked examples (printed pp. 52-53) and cross-checked character-for-character against DWSIM's open SourWater reaction file. The k5 coefficient D uses the report's 2.5551e11 (DWSIM's file carries the digit-dropped 2.555e11 — the report's value reproduces the report's printed 100 C k5 anchor). In the Henry corrections, CAS is free NH3, CS total acid-gas H2S, and CC total CO2 species (CC = 0 for the NH3-H2S-H2O system).

## Literature anchors (spec T-09, tolerance 10 %)

H2S partial pressure over a pH-7.00 buffered H2S 0.010-m solution vs the report's Table 21 API column:

| T (C) | reference (mmHg) | model (mmHg) | deviation |
| --- | --- | --- | --- |
| 80 | 59.3 | 59.33 | +0.1 % |
| 100 | 60.1 | 60.14 | +0.1 % |
| 120 | 61.8 | 61.83 | +0.1 % |
| 140 | 68.0 | 68.80 | +1.2 % |

The spec's acceptance point (90 C within 10 %): the report's table has no 90 C row; linearly interpolating the API values at 80/100 C gives the 59.70-mmHg anchor, and the model lands 59.89 mmHg, +0.32 % — inside the tolerance with margin.

Known applicability limit — EPA Table 19 (Terres NH3-H2S-H2O data): the model reproduces the 40 C rows well (worst +15.7 % NH3, +8.1 % H2S) and the 60 C rows on 2 of 4 points, but the 28 C rows deviate up to +230 % on H2S. The report's own two calculated columns (VK and API) disagree with each other by up to 65 % on the same rows, so the API column's exact variant is not pinned by the report text; applying the report's ionic-strength correction to k5 (hypothesised fix) over-corrects to -90 % and was rejected. The scatter is a declared limit of this implementation: rely on the 40-100 C range (the catalogue row's window starts at 20 C for interpolation continuity but the anchors below 40 C are the weak ones).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 311.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 0 | 311.15K/5e+06Pa T_ph 0 H 0 T_ps 0 |
| determinism | ok | 0 | two instances bit-identical at 311.15K/5e+06Pa |

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented; the spec's acceptance criteria carry no reactive cp), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat, f_i == p_eq_i phi_i^V), not a Gibbs-excess composition derivative; the Gibbs-Duhem identity at fixed T, P is not the composition-consistency surface here — flash consistency is pinned by the T-09 tests instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency y_i P == p_eq_i is pinned by the T-09 tests)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## Scope notes

- Speciation is exact given the constants: the association/dissociation equilibria solve to closed-form species fractions at a charge-balance pH found by bisection; partial pressures follow p_i [mmHg] = H_i * c_i,free * 51.7149.
- Phase split: stability is classified at the feed composition and one Rachford-Rice split is taken at those feed K-values. This is exact at the saturation boundaries (where the K-values are formed at the phase's own composition) and an approximation mid-two-phase-region; the composition dependence of reactive K-values makes iterative re-splitting oscillate (documented in the adapter docstring).
- CO2-bearing sour water is refused at first use: the carbonate constants exist in the same source table but no CO2 anchor was verified this session (documented refusal, not silent omission).

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Wilson, G. M., "A New Correlation of NH3, H2S, and CO2 Volatility Data into Aqueous Sour Water Systems", EPA-600/2-80-067, March 1980 (https://nepis.epa.gov/Exe/ZyPDF.cgi?Dockey=9101B309.PDF)
- Shih, T.-P. et al. (Table 21 H2S buffered-solution data) and Terres, E. et al. (Table 19 NH3-H2S-H2O data) as reproduced in the EPA report
- DWSIM SourWater implementation (FlashAlgorithms/SourWater.vb, DanWBR/dwsim) — cross-check of the reaction and Henry constants
