# vanlaar_nothnagel — van Laar liquid + Nothnagel virial vapour — Tsonopoulos (fallback)

family `gamma_phi` · status **validated** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: Nothnagel (1973) b/K parameter table not available from open sources; the row builds the declared Tsonopoulos-extended second-virial fallback (ngdesign.thermo.virial) (spec deviation)
- provenance: real second-virial phase via the declared Tsonopoulos-extended fallback; the row name identifies that Nothnagel parameters remain unavailable (spec deviation)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 6.5e-16 | 380K/50000Pa T_ph 1.5e-16 H 6.5e-16 T_ps 3e-16; 400K/100000Pa T_ph 0 H 0 T_ps 1.4e-16 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 57.1826 dH/dT 57.1826 |
| gibbs_duhem | ok | 5.5e-09 | ['EtOH', 'H2O']@350K/100000Pa aqueous 5.5e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: van Laar binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/vanlaar/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support

## L1/L2 reference-case outcomes

44/55 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ddb549-etohh2o-50.66kPa-x0.0855` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.0855, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.3495` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.3495, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.7` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.7, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `vanlaar-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21
- `vanlaar-ig-pure-H2O-340K` — coolprop:Water
- `vanlaar-ig-pure-H2O-370K` — coolprop:Water
- `vanlaar-ig-pure-MeOH-305K` — coolprop:Methanol
- `vanlaar-ig-pure-MeOH-330K` — coolprop:Methanol
- `t1r-nrtl-etohh2o-101.3kPa-369.27K-x0.015` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-365.61K-x0.035` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-359.79K-x0.100` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-356.66K-x0.183` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-354.88K-x0.292` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-353.89K-x0.394` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-353.06K-x0.501` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-352.73K-x0.543` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-352.04K-x0.631` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-351.67K-x0.749` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-351.64K-x0.794` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-351.40K-x0.848` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-351.33K-x0.899` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-351.37K-x0.949` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 9+10; retrieved 2026-11-04
- `t1r-nrtl-etohh2o-101.3kPa-azeotrope` — Lai, H.-S.; Lin, Y.-F.; Tu, C.-H., J. Chem. Thermodyn. 68 (2014) 13-19, DOI 10.1016/j.jct.2013.08.020, binary ethanol(1)+water(2) isobaric VLE at 101.3 kPa (constituent-binary subset of the ternary study), via open NIST ThermoML XML https://trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml, ThermoML datasets 11+12 (azeotropic temperature and composition); retrieved 2026-11-04

## References

- Nothnagel, K.-H., Abrams, D. S. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 12(1), 25-35, 1973 (b/K parameter table not available from open sources)
- Tsonopoulos, C., AIChE J. 20(2), 263-272, 1974 (extended correlation used by the declared fallback)
