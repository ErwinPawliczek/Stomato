# margules_hoc — Margules liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **validated** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

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
| round_trip | ok | 7.6e-15 | 380K/50000Pa T_ph 1.3e-15 H 7.6e-15 T_ps 2.4e-15; 400K/100000Pa T_ph 2.8e-16 H 4.3e-15 T_ps 2.7e-15 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 58.1648 dH/dT 58.1648 |
| gibbs_duhem | ok | 4.5e-09 | ['EtOH', 'H2O']@350K/100000Pa aqueous 4.5e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: Margules binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/margules/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support

## L1/L2 reference-case outcomes

31/35 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ddb4731-h2omeg-3.333kPa-x0.1` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.1, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.404` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.404, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.706` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.706, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.0855` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.0855, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.3495` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.3495, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.7` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.7, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `margules-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21
- `margules-ig-megh2o-383.15K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `margules-ig-megh2o-431.25K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `margules-ig-pure-H2O-340K` — coolprop:Water
- `margules-ig-pure-H2O-370K` — coolprop:Water
- `margules-ig-pure-MeOH-305K` — coolprop:Methanol
- `margules-ig-pure-MeOH-330K` — coolprop:Methanol

## References

- Hayden, R. S. & O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equations; open transcriptions Lehigh 1986 MSc thesis Appendix A, COBEQ-2014, Maiorella LBL report LBL-1991)
- Prausnitz, J. M., Anderson, T., Grens, E., Eckert, C., Hsieh, R. & O'Connell, J. P., Computer Calculations for Multicomponent Vapor-Liquid and Liquid-Liquid Equilibria, Prentice-Hall, 1980 (BIJS2 Fortran; eta table via ChemSep Lite 8.50 HAYDENO.IPD)
