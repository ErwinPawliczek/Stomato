# unifac_psrk_ig — UNIFAC (PSRK) liquid + ideal gas vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: thermo 0.6.1 bundled UNIFAC PSRK interaction and subgroup tables (load_unifac_ip)
- provenance: curated per-component group assignments in data/thermo_params/unifac/groups.yaml - a component outside the curated set raises rather than predicting

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 1.5e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 1.4e-16 |
| dhdT_cp | ok | 6e-08 | 380K/50000Pa vapor cp 42.0432 dH/dT 42.0432 |
| gibbs_duhem | ok | 8.8e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 8.8e-09 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C2 (74-84-0) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

4/4 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `unifac-psrk-ig-meohnc4-323.22K-0.3366MPa` — Courtial, Soo, Coquelet, Paricaud, Ramjugernath & Richon (2009) Fluid Phase Equilib. 277, pp. 152-161, Table 4, 323.22 K isotherm; retrieved 2026-10-21
- `unifac-psrk-ig-etohh2o-azeotrope-101.325kPa` — Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21

## References

- Holderbaum, T. & Gmehling, J., Fluid Phase Equilib. 70(2-3), 251-265, 1991
