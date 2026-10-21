# unifac_lle_rk — UNIFAC-LLE liquid + Redlich-Kwong vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: thermo 0.6.1 bundled UNIFAC LLE interaction and subgroup tables (load_unifac_ip)
- provenance: curated per-component group assignments in data/thermo_params/unifac/groups.yaml - a component outside the curated set raises rather than predicting

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | H2O@300K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | H2O@350K ok; H2O@400K ok |
| round_trip | ok | 4.3e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 0; 400K/100000Pa T_ph 0 H 0 T_ps 4.3e-16 |
| dhdT_cp | ok | 3.1e-08 | 380K/50000Pa vapor cp 77.0714 dH/dT 77.0714 |
| gibbs_duhem | ok | 4.7e-09 | ['H2O', 'nC4']@350K/100000Pa aqueous 4.7e-09; ['H2O', 'nC4']@380K/50000Pa vapor 1.7e-10 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['aqueous'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Magnussen, T., Rasmussen, P. & Fredenslund, A., Ind. Eng. Chem. Process Des. Dev. 20(2), 331-339, 1981
