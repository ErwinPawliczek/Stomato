# unifac_lle_hoc — UNIFAC-LLE liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **experimental** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: no verifiable, citable equation/parameter table found (DWSIM's implementation is GPLv3 and must not be copied)
- provenance: the row registers as experimental and its builder refuses rather than inventing physics - see ngdesign.thermo.virial (spec deviation)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| phase_identification | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| round_trip | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| dhdT_cp | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| gibbs_duhem | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| determinism | FAIL | n/a | raised ValueError: no UNIFAC group assignment for MeOH (67-56-1) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |
| single_liquid_limit | FAIL | n/a | raised ValueError: no UNIFAC group assignment for EtOH (64-17-5) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems) |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Hayden-O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equation reference; no verifiable open parameter table found this session)
- Nothnagel, K.-H., Abrams, D. S. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 12(1), 25-35, 1973 (equation reference; same parameter-table gap)
