# pc_saft_assoc — PC-SAFT with association (hand-rolled kernel)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:PCSaftAssocThermo`.

## Applicability (Carlson 1996)

- component classes: water, alcohol
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: hand-rolled PC-SAFT + Wertheim association kernel, G&S 2002 parameters (data/thermo_params/saft/pure.yaml)
- provenance: physical term (hard chain + dispersion) reimplemented from Gross & Sadowski (2001) Ind. Eng. Chem. Res. 40, 1244-1257 with closed-form density and composition derivatives, pinned to teqp's PC-SAFT engine by a check-value test (alpha agreement 4.4e-15 relative over 300-500 K, 100-15000 mol/m3); association term (2B scheme for every fluid, G&S 2002 eqs. 2-3 combining rules) from Gross & Sadowski (2002) Ind. Eng. Chem. Res. 41, 5510-5515 Table 1, retrieved and typed this session (2026-10-23); site fractions by the shared successive-substitution solver (Michelsen & Hendriks 2001); k_ij = 0 — the paper introduces no binary interaction parameter for associating-associating mixtures ("simple combining rules were used")

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@373.15K bubble 0 dew 0; H2O@423.15K bubble 0 dew 0; MeOH@337.7K bubble 0 dew 0; EtOH@351.45K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@373.15K ok; MeOH@320K ok |
| round_trip | ok | 1.6e-07 | 350K/300000Pa T_ph 1.6e-07 H 8.7e-08 T_ps 1.1e-07 |
| dhdT_cp | ok | 0 | 400K/100000Pa vapor cp 38.1177 dH/dT 38.1177 |
| gibbs_duhem | ok | 1.2e-07 | ['H2O', 'MeOH']@400K/100000Pa vapor 1.2e-08; ['H2O', 'MeOH']@350K/300000Pa aqueous 1.2e-07 |
| single_liquid_limit | ok | 0 | 373.15K/300000Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 400K/100000Pa |

Note: T-17 step B promoted the row from refusal to provisional on 2026-10-23: teqp's PC-SAFT factory carries no association-parameter fields, so the row runs the bridge's hand-rolled kernel — teqp-pinned PC-SAFT physical term plus the shared saft_assoc association solver with the G&S (2002) Table 1 two-site parameters and k_ij = 0 per the paper's own combining rule for associating-associating mixtures.

## L1/L2 reference-case outcomes

57/112 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-H2O-323.5K-ps` — coolprop:Water
- `pure-H2O-420.0K-ps` — coolprop:Water
- `pure-H2O-520.0K-ps` — coolprop:Water
- `pure-H2O-600.0K-ps` — coolprop:Water
- `pure-H2O-614.7K-ps` — coolprop:Water
- `pure-MeOH-256.3K-ps` — coolprop:Methanol
- `pure-MeOH-307.6K-ps` — coolprop:Methanol
- `pure-MeOH-358.8K-ps` — coolprop:Methanol
- `pure-MeOH-410.1K-ps` — coolprop:Methanol
- `pure-MeOH-461.3K-ps` — coolprop:Methanol
- `pure-EtOH-300.0K-ps` — coolprop:Ethanol
- `pure-EtOH-351.45K-ps` — coolprop:Ethanol
- `pure-EtOH-420.0K-ps` — coolprop:Ethanol
- `pure-EtOH-480.0K-ps` — coolprop:Ethanol
- `meohh2o-322.91K-15.932kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-26.131kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-31.544kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-40.850kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-46.450kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-52.142kPa-ps` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-101.325kPa-353.25K-ps` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-349.05K-ps` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-101.325kPa-346.20K-ps` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `meohh2o-323.15K-x0.9785-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.9340-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.8674-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.7484-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.6408-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.5564-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.4482-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.3274-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.2589-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.1788-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.1123-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09
- `meohh2o-323.15K-x0.0621-bern` — Bernatova, Aim & Wichterle (2006) Isothermal vapour-liquid equilibrium with chemical reaction in the quaternary water + methanol + acetic acid + methyl acetate system, and in five binary subsystems, Fluid Phase Equilib. 247, 96-101, DOI 10.1016/j.fluid.2006.06.005; binary methanol + water at 323.15 K (circulation ebulliometer P, GC vapour analysis), NIST TRC ThermoML archive file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2006.06.005.xml data sets 5 (P) and 6 (y_water); x/y printed as WATER mole fractions, keyed here per component (MeOH = 1 - water); retrieved 2026-11-09

## References

- Gross & Sadowski, "Application of the Perturbed-Chain SAFT Equation of State to Associating Systems", Ind. Eng. Chem. Res. 41 (2002) 5510-5515
- Gross & Sadowski, "Perturbed-Chain SAFT: An Equation of State Based on a Perturbation Theory for Chain Molecules", Ind. Eng. Chem. Res. 40 (2001) 1244-1257
- Michelsen & Hendriks, "Physical properties from association models", Fluid Phase Equilib. 180 (2001) 165-174
