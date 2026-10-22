# regular_solution_hoc — regular solution liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: Hayden-O'Connell (1975) equation set transcribed from open sources (Lehigh 1986 MSc thesis Appendix A; COBEQ-2014 proceedings paper; the Prausnitz-1980 book BIJS2 Fortran as printed in the Maiorella LBL report LBL-1991); eta table data/thermo_params/virial/hoc_eta.yaml from ChemSep Lite 8.50 HAYDENO.IPD
- provenance: real second-virial kernel in ngdesign.thermo.virial; slates with a pure eta >= 4.0 component refuse (the Prausnitz-1980 apparent-fugacity correction for strongly associating vapours is not available from open sources; use hoc_dimer for acids)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 9.5e-15 | 380K/50000Pa T_ph 0 H 0 T_ps 7.5e-16; 400K/100000Pa T_ph 9.5e-15 H 0 T_ps 5.4e-15 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 44.3086 dH/dT 44.3086 |
| gibbs_duhem | ok | 1.5e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.5e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 6e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Hayden, R. S. & O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equations; open transcriptions Lehigh 1986 MSc thesis Appendix A, COBEQ-2014, Maiorella LBL report LBL-1991)
- Prausnitz, J. M., Anderson, T., Grens, E., Eckert, C., Hsieh, R. & O'Connell, J. P., Computer Calculations for Multicomponent Vapor-Liquid and Liquid-Liquid Equilibria, Prentice-Hall, 1980 (BIJS2 Fortran; eta table via ChemSep Lite 8.50 HAYDENO.IPD)
