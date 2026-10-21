# cpa_srk — CPA-SRK (hand-rolled association kernel)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:CpaSrkThermo`.

## Applicability (Carlson 1996)

- component classes: water, alcohol
- polar: True · electrolyte: False
- T window: 250–620 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: CPA-SRK, Kontogeorgis parameters (data/thermo_params/saft/pure.yaml)
- provenance: water 4C and methanol 2B CPA parameters from Kontogeorgis, Voutsas, Yakoumis & Tassios (1996) Ind. Eng. Chem. Res. 35, 4631-4642, retrieved and verified this session against Table 1 of Kontogeorgis et al. (1999) Fluid Phase Equilib. 158-160, 21-29; SRK cubic term closed-form, association term by successive substitution (Michelsen-Hendriks); k_ij = 0 — no verifiable open citation for the water-methanol CPA k_ij was found

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@373.15K bubble 0 dew 0; H2O@423.15K bubble 0 dew 0; MeOH@337.7K bubble 0 dew 0; MeOH@298.15K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@373.15K ok; MeOH@320K ok |
| round_trip | ok | 1.4e-07 | 350K/300000Pa T_ph 1.4e-07 H 8.4e-08 T_ps 1.4e-07 |
| dhdT_cp | ok | 0 | 400K/100000Pa vapor cp 39.5898 dH/dT 39.5898 |
| gibbs_duhem | ok | 5.6e-07 | ['H2O', 'MeOH']@400K/100000Pa vapor 5.6e-07; ['H2O', 'MeOH']@350K/300000Pa aqueous 5.7e-08 |
| single_liquid_limit | ok | 0 | 373.15K/300000Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 400K/100000Pa |

Note: teqp 0.23.2's own CPA engine NaNs its fugacity coefficients at liquid-like densities and collapses the water saturation line with the published Kontogeorgis parameters, so this row runs the bridge's hand-rolled CPA-SRK kernel instead (measured in the T-07 exploration).

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

Declared case ids:

- `pure-H2O-323.5K` — coolprop:Water
- `pure-H2O-420.0K` — 
- `pure-H2O-520.0K` — 
- `pure-H2O-600.0K` — 
- `pure-H2O-614.7K` — coolprop:Water
- `pure-MeOH-256.3K` — 
- `pure-MeOH-307.6K` — 
- `pure-MeOH-358.8K` — 
- `pure-MeOH-410.1K` — 
- `pure-MeOH-461.3K` — 
- `meohh2o-97.99kPa-353.25K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-349.05K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-343.75K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-322.91K-15.932kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-26.131kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-31.544kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-40.850kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-46.450kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-52.142kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20

## References

- Kontogeorgis, Voutsas, Yakoumis & Tassios, "An Equation of State for Associating Fluids", Ind. Eng. Chem. Res. 35 (1996) 4631-4642
- Kontogeorgis, Yakoumis, Meijer, Hendriks & Moorwood, "Multicomponent phase equilibrium calculations for water-methanol-alkane mixtures", Fluid Phase Equilib. 158-160 (1999) 201-209
