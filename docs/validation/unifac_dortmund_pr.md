# unifac_dortmund_pr — UNIFAC (Dortmund) liquid + Peng-Robinson vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: thermo 0.6.1 bundled UNIFAC Dortmund interaction and subgroup tables (load_unifac_ip)
- provenance: curated per-component group assignments in data/thermo_params/unifac/groups.yaml - a component outside the curated set raises rather than predicting

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 4.3e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 4.3e-16 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.2404 dH/dT 42.2404 |
| gibbs_duhem | ok | 5e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 5e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 2.8e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gmehling, J., Li, J. & Schiller, M., Ind. Eng. Chem. Res. 32(1), 178-193, 1993
