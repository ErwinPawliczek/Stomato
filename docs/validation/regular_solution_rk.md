# regular_solution_rk — regular solution liquid + Redlich-Kwong vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: pure solubility parameters SP_i = sqrt(dHvap_i(T)/V_i(T,P)) from the thermo pure-component correlations at 298.15 K (EnthalpyVaporizations, VolumeLiquids)
- provenance: components whose correlation returns no value raise rather than default

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 3.4e-16 | 380K/50000Pa T_ph 1.5e-16 H 2.8e-16 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 3.4e-16 T_ps 0 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.248 dH/dT 42.248 |
| gibbs_duhem | ok | 1.5e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.5e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 7.5e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support

## L1/L2 reference-case outcomes

27/62 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ddb11-acetoneh2o-101.33kPa-x0.736` — Reinders W.; de Minjer C.H.: VI. The System Water-Acetone-Chloroform. Recl.Trav.Chim.Pays-Bas 66 (1947) 573-604; data via Dortmund Data Bank Explorer Edition free data page 'VLE Acetone + Water', DDB data set 11 (isobaric 101.33 kPa), data table row x1=0.736, archived copy https://web.archive.org/web/20231003205944/http://www.ddbst.com/en/EED/VLE/VLE%20Acetone%3BWater.php; retrieved 2026-11-04
- `ddb133-meohnc6-333.15K-x0.098` — Scheller M.; Schuberth H.; Koennecke H.G.: Ergebnisse von Dampfflüssigkeits-Phasengleichgewichtsuntersuchungen am System n-Hexan-Methylcyclohexan-Methanol bei 60°C. J.Prakt.Chem. 311 (1969) 974-982; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Hexane', DDB data set 133 (isothermal 333.15 K), data table row x1=0.098, archived copy https://web.archive.org/web/20230930054505/http://www.ddbst.com/en/EED/VLE/VLE%20Hexane%3BMethanol.php; retrieved 2026-11-04
- `ddb133-meohnc6-333.15K-x0.399` — Scheller M.; Schuberth H.; Koennecke H.G.: Ergebnisse von Dampfflüssigkeits-Phasengleichgewichtsuntersuchungen am System n-Hexan-Methylcyclohexan-Methanol bei 60°C. J.Prakt.Chem. 311 (1969) 974-982; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Hexane', DDB data set 133 (isothermal 333.15 K), data table row x1=0.399, archived copy https://web.archive.org/web/20230930054505/http://www.ddbst.com/en/EED/VLE/VLE%20Hexane%3BMethanol.php; retrieved 2026-11-04
- `ddb133-meohnc6-333.15K-x0.733` — Scheller M.; Schuberth H.; Koennecke H.G.: Ergebnisse von Dampfflüssigkeits-Phasengleichgewichtsuntersuchungen am System n-Hexan-Methylcyclohexan-Methanol bei 60°C. J.Prakt.Chem. 311 (1969) 974-982; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Hexane', DDB data set 133 (isothermal 333.15 K), data table row x1=0.733, archived copy https://web.archive.org/web/20230930054505/http://www.ddbst.com/en/EED/VLE/VLE%20Hexane%3BMethanol.php; retrieved 2026-11-04
- `ddb451-meohetoh-101.33kPa-x0.134` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.134, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb451-meohetoh-101.33kPa-x0.401` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.401, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb451-meohetoh-101.33kPa-x0.728` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Methanol + Ethanol', DDB data set 451 (isobaric 101.33 kPa), data table row x1=0.728, archived copy https://web.archive.org/web/20221009034640/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BMethanol.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.1` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.1, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.404` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.404, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb4731-h2omeg-3.333kPa-x0.706` — Sokolov N.M.; Tsygankova L.N.; Zhavoronkov N.M.: The Liquid - Vapor Equilibrium in the Water - Ethylene Glycol and Water - 1,2 - Proylene Glycol Systems at Various Pressures. Theor.Found.Chem.Eng. 5 (1971) 817-820; data via Dortmund Data Bank Explorer Edition free data page 'VLE Water + 1,2-Ethanediol', DDB data set 4731 (isobaric 3.333 kPa), data table row x1=0.706, archived copy https://web.archive.org/web/20230324033715/http://www.ddbst.com/en/EED/VLE/VLE%201%2C2-Ethanediol%3BWater.php; retrieved 2026-11-04
- `ddb521-nc6etoh-101.33kPa-x0.08` — Sinor J.E.; Weber J.H.:; data via Dortmund Data Bank Explorer Edition free data page 'VLE Hexane + Ethanol', DDB data set 521 (isobaric 101.33 kPa), data table row x1=0.08, archived copy https://web.archive.org/web/20231003210219/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BHexane.php; retrieved 2026-11-04
- `ddb521-nc6etoh-101.33kPa-x0.452` — Sinor J.E.; Weber J.H.:; data via Dortmund Data Bank Explorer Edition free data page 'VLE Hexane + Ethanol', DDB data set 521 (isobaric 101.33 kPa), data table row x1=0.452, archived copy https://web.archive.org/web/20231003210219/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BHexane.php; retrieved 2026-11-04
- `ddb521-nc6etoh-101.33kPa-x0.725` — Sinor J.E.; Weber J.H.:; data via Dortmund Data Bank Explorer Edition free data page 'VLE Hexane + Ethanol', DDB data set 521 (isobaric 101.33 kPa), data table row x1=0.725, archived copy https://web.archive.org/web/20231003210219/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BHexane.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.3495` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.3495, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.7` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.7, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb586-acetonemeoh-101.33kPa-x0.081` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Acetone + Methanol', DDB data set 586 (isobaric 101.33 kPa), data table row x1=0.081, archived copy https://web.archive.org/web/20231003035858/http://www.ddbst.com/en/EED/VLE/VLE%20Acetone%3BMethanol.php; retrieved 2026-11-04
- `ddb586-acetonemeoh-101.33kPa-x0.683` — Amer H.H.; Paxton R.R.; van Winkle M.: Vapor-liquid equilibria. Ind.Eng.Chem. 48 (1956) 142-146; data via Dortmund Data Bank Explorer Edition free data page 'VLE Acetone + Methanol', DDB data set 586 (isobaric 101.33 kPa), data table row x1=0.683, archived copy https://web.archive.org/web/20231003035858/http://www.ddbst.com/en/EED/VLE/VLE%20Acetone%3BMethanol.php; retrieved 2026-11-04
- `regular-solution-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21
- `regular-solution-ig-megh2o-383.15K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `regular-solution-ig-megh2o-431.25K-101.325kPa` — Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- `regular-solution-ig-meohh2o-101.325kPa-349.05K` — Gao, Zhang, Lücking, Sun, Si, Zhu, Chen & Shi (2012) J. Thermodynamics, Article ID 641251, DOI 10.1155/2012/641251, Table 3, isobaric 101.325 kPa (T, x measured by pump ebulliometer; y calculated via the T,p,x,HmE indirect method); open access; retrieved 2026-10-22
- `regular-solution-ig-meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `regular-solution-ig-pure-H2O-340K` — coolprop:Water
- `regular-solution-ig-pure-H2O-370K` — coolprop:Water
- `regular-solution-ig-pure-MeOH-305K` — coolprop:Methanol
- `regular-solution-ig-pure-MeOH-330K` — coolprop:Methanol

## References

- Scatchard, G., Chem. Rev. 8(2), 321-333, 1931
- Hildebrand, J. H. & Scott, R. L., The Solubility of Nonelectrolytes, 3rd ed., 1950
