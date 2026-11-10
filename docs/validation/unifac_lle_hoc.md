# unifac_lle_hoc — UNIFAC-LLE liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

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
| pure_psat_limit | ok | 0 | H2O@300K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@350K ok; H2O@400K ok |
| round_trip | ok | 9.3e-15 | 380K/50000Pa T_ph 3e-16 H 2e-15 T_ps 9e-16; 400K/100000Pa T_ph 4.3e-16 H 9.3e-15 T_ps 9.9e-16 |
| dhdT_cp | ok | 0 | 380K/50000Pa vapor cp 77.537 dH/dT 77.537 |
| gibbs_duhem | ok | 4.7e-09 | ['H2O', 'nC4']@350K/100000Pa aqueous 4.7e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['aqueous'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE table, for example, has no methanol subgroup)

## L1/L2 reference-case outcomes

4/12 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `unifac-pure-H2O-meohh2o-66.52kPa` — Yang, Sun, Ma, Yin & Zeng (2012) "Organic Salt Effect on Vapor-Liquid Equilibrium of the Methanol + Water System at Subatmospheric Pressure", J. Chem. Eng. Data 57, 2696-2701, doi:10.1021/je300613v; salt-free methanol + water series, recirculating-still T-x, y by gas chromatography, 66.52 kPa; pure-H2O endpoint of the series (measured boiling T at P); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je300613v.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 1; retrieved 2026-11-04
- `unifac-pure-nC4-meohnc4-364.5K` — Dell'Era, Zaytseva, Uusi-Kyyny, Pokki, Pakkanen & Aittamaa (2007) "Vapour liquid equilibrium for the systems butane + methanol, +2-propanol, +1-butanol, +2-butanol, +2-methyl-2-propanol at 364.5 K", Fluid Phase Equilib. 254, 49-59, doi:10.1016/j.fluid.2007.02.028; static total-pressure P-x at 364.5 K (the paper's y are Barker-calculated, not measured, so only P is compared); pure-nC4 endpoint of the series (measured vapour pressure at T); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2007.02.028.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 7; retrieved 2026-11-04
- `unifac-pure-nC4-etohnc4-333.2K` — Machida, Matsumura & Horizoe (2014) "High pressure vapor-liquid equilibria measurements and modeling of butane/ethanol system and isobutane/ethanol system", Fluid Phase Equilib. 375, 176-180, doi:10.1016/j.fluid.2014.05.018; recirculating-still P-x, y by gas chromatography, 333.2 K isotherm; pure-nC4 endpoint of the series (measured vapour pressure at T); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1016/j.fluid.2014.05.018.xml (archive ThermoML.v2020-09-30, data.nist.gov mds2-2422), PureOrMixtureData set 4; retrieved 2026-11-04
- `unifac-lle-buh2o-101.3kPa-323.15K-organic` — Lladosa, Monton, Burguet & Munoz (2008) "Phase Equilibrium for the Esterification Reaction of Acetic Acid + Butan-1-ol at 101.3 kPa", J. Chem. Eng. Data 53, 108-115, doi:10.1021/je700411p; binary butan-1-ol + water LLE tie-lines at 101.3 kPa; organic-rich liquid (Liquid mixture 1) at 323.15 K: ThermoML PureOrMixtureData set 14 (mole fraction of butan-1-ol = 0.4574); feed z = mid-point of the tie-line with the water-rich liquid (set 15, butan-1-ol = 0.0167); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je700411p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-buh2o-101.3kPa-343.15K-organic` — Lladosa, Monton, Burguet & Munoz (2008) "Phase Equilibrium for the Esterification Reaction of Acetic Acid + Butan-1-ol at 101.3 kPa", J. Chem. Eng. Data 53, 108-115, doi:10.1021/je700411p; binary butan-1-ol + water LLE tie-lines at 101.3 kPa; organic-rich liquid (Liquid mixture 1) at 343.15 K: ThermoML PureOrMixtureData set 14 (mole fraction of butan-1-ol = 0.4189); feed z = mid-point of the tie-line with the water-rich liquid (set 15, butan-1-ol = 0.0172); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je700411p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-buh2o-101.3kPa-362.45K-organic` — Lladosa, Monton, Burguet & Munoz (2008) "Phase Equilibrium for the Esterification Reaction of Acetic Acid + Butan-1-ol at 101.3 kPa", J. Chem. Eng. Data 53, 108-115, doi:10.1021/je700411p; binary butan-1-ol + water LLE tie-lines at 101.3 kPa; organic-rich liquid (Liquid mixture 1) at 362.45 K: ThermoML PureOrMixtureData set 14 (mole fraction of butan-1-ol = 0.3673); feed z = mid-point of the tie-line with the water-rich liquid (set 15, butan-1-ol = 0.0187); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je700411p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-eah2o-101.3kPa-298.15K-organic` — Grande & Marschoff (2005) "Liquid-Liquid Equilibria for Water + Benzonitrile + Ethyl Acetate or + Butyl Acetate", J. Chem. Eng. Data 50, 1324-1327, doi:10.1021/je050051h; binary water + ethyl acetate mutual solubilities at 101.3 kPa; organic-rich liquid (Liquid mixture 2) at 298.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of water = 0.1733); feed z = mid-point of the tie-line with the water-rich liquid (set 1, water = 0.9837); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je050051h.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-eah2o-101.3kPa-313.15K-organic` — Grande & Marschoff (2005) "Liquid-Liquid Equilibria for Water + Benzonitrile + Ethyl Acetate or + Butyl Acetate", J. Chem. Eng. Data 50, 1324-1327, doi:10.1021/je050051h; binary water + ethyl acetate mutual solubilities at 101.3 kPa; organic-rich liquid (Liquid mixture 2) at 313.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of water = 0.2111); feed z = mid-point of the tie-line with the water-rich liquid (set 1, water = 0.9856); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je050051h.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-eah2o-101.3kPa-333.15K-organic` — Grande & Marschoff (2005) "Liquid-Liquid Equilibria for Water + Benzonitrile + Ethyl Acetate or + Butyl Acetate", J. Chem. Eng. Data 50, 1324-1327, doi:10.1021/je050051h; binary water + ethyl acetate mutual solubilities at 101.3 kPa; organic-rich liquid (Liquid mixture 2) at 333.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of water = 0.2414); feed z = mid-point of the tie-line with the water-rich liquid (set 1, water = 0.9867); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je050051h.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-peh2o-101.33kPa-293.15K-organic` — Huang, Chen, Wang & Wang (2011) "Liquid-Liquid Equilibria of Water + Pentan-1-ol + 2,6,6-Trimethylbicyclo[3.1.1]hep-2-ene or 6,6-Dimethyl-2-methylenebicyclo[3.1.1]heptane at (293.15, 303.15, 313.15, and 323.15) K", J. Chem. Eng. Data 56, 1249-1254, doi:10.1021/je101119p; binary water + pentan-1-ol tie-lines at 101.33 kPa; organic-rich liquid (Liquid mixture 1) at 293.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of pentan-1-ol = 0.6562); feed z = mid-point of the tie-line with the water-rich liquid (set 1, pentan-1-ol = 0.0049); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je101119p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-peh2o-101.33kPa-303.15K-organic` — Huang, Chen, Wang & Wang (2011) "Liquid-Liquid Equilibria of Water + Pentan-1-ol + 2,6,6-Trimethylbicyclo[3.1.1]hep-2-ene or 6,6-Dimethyl-2-methylenebicyclo[3.1.1]heptane at (293.15, 303.15, 313.15, and 323.15) K", J. Chem. Eng. Data 56, 1249-1254, doi:10.1021/je101119p; binary water + pentan-1-ol tie-lines at 101.33 kPa; organic-rich liquid (Liquid mixture 1) at 303.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of pentan-1-ol = 0.6484); feed z = mid-point of the tie-line with the water-rich liquid (set 1, pentan-1-ol = 0.0047); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je101119p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)
- `unifac-lle-peh2o-101.33kPa-323.15K-organic` — Huang, Chen, Wang & Wang (2011) "Liquid-Liquid Equilibria of Water + Pentan-1-ol + 2,6,6-Trimethylbicyclo[3.1.1]hep-2-ene or 6,6-Dimethyl-2-methylenebicyclo[3.1.1]heptane at (293.15, 303.15, 313.15, and 323.15) K", J. Chem. Eng. Data 56, 1249-1254, doi:10.1021/je101119p; binary water + pentan-1-ol tie-lines at 101.33 kPa; organic-rich liquid (Liquid mixture 1) at 323.15 K: ThermoML PureOrMixtureData set 2 (mole fraction of pentan-1-ol = 0.6245); feed z = mid-point of the tie-line with the water-rich liquid (set 1, pentan-1-ol = 0.0042); NIST TRC ThermoML file https://trc.nist.gov/ThermoML/10.1021/je101119p.xml; retrieved 2026-11-04 (re-retrieved 2026-11-09)

## References

- Hayden, R. S. & O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equations; open transcriptions Lehigh 1986 MSc thesis Appendix A, COBEQ-2014, Maiorella LBL report LBL-1991)
- Prausnitz, J. M., Anderson, T., Grens, E., Eckert, C., Hsieh, R. & O'Connell, J. P., Computer Calculations for Multicomponent Vapor-Liquid and Liquid-Liquid Equilibria, Prentice-Hall, 1980 (BIJS2 Fortran; eta table via ChemSep Lite 8.50 HAYDENO.IPD)
