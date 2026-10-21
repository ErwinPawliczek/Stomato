# nrtl — NRTL liquid + Peng-Robinson vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.nrtl:NrtlThermo`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep), 'ChemSep NRTL' binary table
- provenance: Renon, H. & Prausnitz, J. M., 'Local Compositions in Thermodynamic Excess Functions for Liquid Mixtures', AIChE J. 14(1), 135-144, 1968; binary parameters from the ChemSep IPDB 'NRTL original T' form; databank coverage is limited (MeOH/H2O, MeOH/nC4, MeOH/C6+ pairs)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.3e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 4.3e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2404 dH/dT 42.2404 |
| gibbs_duhem | ok | 9.1e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 9.1e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 2.8e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

Note: pure hydrocarbons are NOT phase-identification points: thermo's pure-component vapour-pressure correlation sits ~8% above the ChemSep databank Psat for nC4 at 300 K (measured condensation at 2.78e5 Pa vs databank 2.58e5 Pa), so a bracket on the databank Psat lands inside the model's own two-phase region; MeOH/H2O correlations agree with the databank and are used instead

### L4 cross-model pairs

- vs `pr`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- vs `pr78`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- vs `srk`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

29/62 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `meohh2o-97.99kPa-369.65K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-365.45K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-360.65K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-353.25K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-349.05K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-343.75K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-341.85K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-97.99kPa-339.55K` — Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- `meohh2o-312.91K-9.079kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-13.012kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-16.319kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-20.705kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-23.385kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-27.518kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-312.91K-32.571kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- `meohh2o-322.91K-15.932kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-26.131kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-31.544kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-40.850kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-46.450kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- `meohh2o-322.91K-52.142kPa` — Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20

## References

- Renon, H. & Prausnitz, J. M., AIChE J. 14(1), 135-144, 1968
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
