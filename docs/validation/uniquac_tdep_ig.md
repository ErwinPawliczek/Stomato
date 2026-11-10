# uniquac_tdep_ig — UNIQUAC T-dependent form + ideal gas vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water
- polar: True · electrolyte: False
- T window: 298.15–373.15 K · P window: 1000–1e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/uniquac/tdep_pairs.yaml
- provenance: tau_ij = exp(a_ij + b_ij / T) and r, q from Guevara Luna et al. 2018, with per-entry provenance in the file; the only pair the row covers, any other refuses

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | EtOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | EtOH@350K ok; H2O@400K ok |
| round_trip | ok | 6.3e-16 | 380K/50000Pa T_ph 1.5e-16 H 6.3e-16 T_ps 4.5e-16; 400K/100000Pa T_ph 0 H 0 T_ps 2.8e-16 |
| dhdT_cp | ok | 2.3e-08 | 380K/50000Pa vapor cp 56.098 dH/dT 56.098 |
| gibbs_duhem | ok | 1e-08 | ['EtOH', 'H2O']@350K/100000Pa aqueous 1e-08 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

## L1/L2 reference-case outcomes

11/13 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `ddb549-etohh2o-50.66kPa-x0.0855` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.0855, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.3495` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.3495, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `ddb549-etohh2o-50.66kPa-x0.7` — Beebe A.H.; Coulter K.E.; Lindsay R.A.; Baker E.M.: Equilibria in Ethanol-Water System at Pressures Less Than Atmospheric. Ind.Eng.Chem. Ind.Ed. 34 (1942) 1501-1504; data via Dortmund Data Bank Explorer Edition free data page 'VLE Ethanol + Water', DDB data set 549 (isobaric 50.66 kPa), data table row x1=0.7, archived copy https://web.archive.org/web/20210302041122/http://www.ddbst.com/en/EED/VLE/VLE%20Ethanol%3BWater.php; retrieved 2026-11-04
- `uniquac-ig-pure-H2O-340K` — coolprop:Water
- `uniquac-ig-pure-H2O-370K` — coolprop:Water

## References

- Abrams, D. S. & Prausnitz, J. M., AIChE J. 21(1), 116-128, 1975
- Guevara Luna, M. A. et al., Tecciencia 13(24), 2018, doi 10.18180/tecciencia.2018.24.3
