# uniquac_hoc — UNIQUAC liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **validated** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: Hayden-O'Connell (1975) equation set transcribed from open sources (Lehigh 1986 MSc thesis Appendix A; COBEQ-2014 proceedings paper; the Prausnitz-1980 book BIJS2 Fortran as printed in the Maiorella LBL report LBL-1991); eta table data/thermo_params/virial/hoc_eta.yaml from ChemSep Lite 8.50 HAYDENO.IPD
- provenance: real second-virial kernel in ngdesign.thermo.virial; slates with a pure eta >= 4.0 component refuse (the Prausnitz-1980 apparent-fugacity correction for strongly associating vapours is not available from open sources; use hoc_dimer for acids)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.4e-14 | 380K/50000Pa T_ph 0 H 0 T_ps 7.5e-16; 400K/100000Pa T_ph 9.5e-15 H 4.4e-14 T_ps 5.4e-15 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 44.3086 dH/dT 44.3086 |
| gibbs_duhem | ok | 8.6e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 8.6e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 6e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

39/45 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ddb451-meohetoh-101.33kPa-x0.134` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.134, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb451-meohetoh-101.33kPa-x0.401` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.401, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb451-meohetoh-101.33kPa-x0.728` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.728, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.1` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.1, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.404` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.404, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.706` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.706, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.0855` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.0855, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.3495` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.3495, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.7` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.7, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `uniquac-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21
- `uniquac-ig-megh2o-383.15K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `uniquac-ig-megh2o-431.25K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `uniquac-ig-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `uniquac-ig-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `uniquac-ig-pure-H2O-340K` — coolprop:Water
- `uniquac-ig-pure-H2O-370K` — coolprop:Water
- `uniquac-ig-pure-MeOH-305K` — coolprop:Methanol
- `uniquac-ig-pure-MeOH-330K` — coolprop:Methanol

## References

- Hayden, R. S. & O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equations; open transcriptions Lehigh 1986 MSc thesis Appendix A, COBEQ-2014, Maiorella LBL report LBL-1991)
- Prausnitz, J. M., Anderson, T., Grens, E., Eckert, C., Hsieh, R. & O'Connell, J. P., Computer Calculations for Multicomponent Vapor-Liquid and Liquid-Liquid Equilibria, Prentice-Hall, 1980 (BIJS2 Fortran; eta table via ChemSep Lite 8.50 HAYDENO.IPD)
