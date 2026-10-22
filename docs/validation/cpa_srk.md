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

Note: teqp 0.23.2's own CPA engine NaNs its fugacity coefficients at liquid-like densities and collapses the water saturation line with the published Kontogeorgis parameters, so this row runs the bridge's hand-rolled CPA-SRK kernel instead (measured in the T-07 exploration). T-15 disposition: teqp is CI-runnable (cp312 wheels) but the row keeps experimental status pending an L0 declaration; its bound cases measured outside tolerance on the T-07 sweep.

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
- `meohh2o-101.325kPa-353.25K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-346.20K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-322.91K-15.932kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-26.131kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-31.544kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-40.850kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-46.450kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-52.142kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20

## References

- Kontogeorgis, Voutsas, Yakoumis & Tassios, "An Equation of State for Associating Fluids", Ind. Eng. Chem. Res. 35 (1996) 4631-4642
- Kontogeorgis, Yakoumis, Meijer, Hendriks & Moorwood, "Multicomponent phase equilibrium calculations for water-methanol-alkane mixtures", Fluid Phase Equilib. 158-160 (1999) 201-209
