# cpa_pr — CPA-PR (hand-rolled association kernel)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:CpaPrThermo`.

## Applicability (Carlson 1996)

- component classes: water, alcohol, glycol
- polar: True · electrolyte: False
- T window: 250–620 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: CPA-PR, Sorensen parameters (data/thermo_params/saft/pure.yaml)
- provenance: water 4C and methanol 2B PR-CPA parameters from Sorensen, Boesen, Leekumjorn & Herslund, "Peng-Robinson Equation of State Extended to Handle Aqueous Components Using CPA Concept", J. Nat. Gas Eng. 6 (2018), DOI 10.7569/JNGE.2018.692501, Table 6, retrieved and typed this session (2026-10-23) from the open-access copy at https://d-nb.info/136523830X/34 with a constant-vs-source check against the printed table; the temperature- dependent water-methanol k_ij is the paper's Table 7 fit; PR cubic term closed-form, association term by the shared successive-substitution solver (Michelsen-Hendriks) with the paper's simplified-CPA radial distribution function (Appendix A eq. A14) and CR-1 combining rules

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@373.15K bubble 0 dew 0; H2O@423.15K bubble 0 dew 0; MeOH@337.7K bubble 0 dew 0; MeOH@298.15K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@373.15K ok; MeOH@320K ok |
| round_trip | ok | 1.5e-07 | 350K/300000Pa T_ph 1.2e-07 H 7.6e-08 T_ps 1.5e-07 |
| dhdT_cp | ok | 0 | 400K/100000Pa vapor cp 38.6886 dH/dT 38.6886 |
| gibbs_duhem | FAIL | 3.7e-06 | ['H2O', 'MeOH']@400K/100000Pa vapor 1.3e-07; ['H2O', 'MeOH']@350K/300000Pa aqueous 3.7e-06 |
| single_liquid_limit | ok | 0 | 373.15K/300000Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 400K/100000Pa |

Note: T-17 promoted the row from refusal to provisional on 2026-10-23: teqp 0.23.2's own CPA engine stays unusable (fugacity NaNs at liquid-like densities, measured in the T-07 exploration), so the row runs the bridge's hand-rolled CPA-PR kernel (PR physical term + the shared saft_assoc association solver) with the Sorensen et al. (2018) Table 6 parameters and the paper's Table 7 temperature-dependent water-methanol k_ij — the k_ij cpa_srk could not carry.

## L1/L2 reference-case outcomes

46/62 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-323.5K-pr` — coolprop:Water
- `pure-H2O-420.0K-pr` — coolprop:Water
- `pure-H2O-520.0K-pr` — coolprop:Water
- `pure-H2O-600.0K-pr` — coolprop:Water
- `pure-H2O-614.7K-pr` — coolprop:Water
- `pure-MeOH-256.3K-pr` — coolprop:Methanol
- `pure-MeOH-307.6K-pr` — coolprop:Methanol
- `pure-MeOH-358.8K-pr` — coolprop:Methanol
- `pure-MeOH-410.1K-pr` — coolprop:Methanol
- `pure-MeOH-461.3K-pr` — coolprop:Methanol
- `meohh2o-322.91K-15.932kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-26.131kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-31.544kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-40.850kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-46.450kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-52.142kPa-pr` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20

## References

- Sorensen, Boesen, Leekumjorn & Herslund, "Peng-Robinson Equation of State Extended to Handle Aqueous Components Using CPA Concept", J. Nat. Gas Eng. 6 (2018), DOI 10.7569/JNGE.2018.692501
- Kontogeorgis, Voutsas, Yakoumis & Tassios, "An Equation of State for Associating Fluids", Ind. Eng. Chem. Res. 35 (1996) 4631-4642
