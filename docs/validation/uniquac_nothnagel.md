# uniquac_nothnagel — UNIQUAC liquid + Nothnagel virial vapour

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
| pure_psat_limit | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| phase_identification | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| round_trip | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| dhdT_cp | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| gibbs_duhem | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| determinism | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |
| single_liquid_limit | FAIL | n/a | raised NotImplementedError: the Nothnagel (1973) second-virial vapour model is not implemented (spec T-03 deviation: no complete, citable open equation set or association-parameter table was verifiable, so the row registers as experimental and refuses to build rather than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr') |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Hayden-O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equation reference; no verifiable open parameter table found this session)
- Nothnagel, K.-H., Abrams, D. S. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 12(1), 25-35, 1973 (equation reference; same parameter-table gap)
