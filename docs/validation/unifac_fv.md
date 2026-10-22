# unifac_fv — UNIFAC free-volume (Oishi-Prausnitz)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:UnifacFvPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 10000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/unifac_fv.yaml
- provenance: Oishi & Prausnitz, Ind. Eng. Chem. Process Des. Dev. 17, 333 (1978): UNIFAC solvent activity plus the Flory free-volume term (c1 = 1.1, 15.17 cm3/mol CH2 reference volume, b = 1.28); polymer activity by Gibbs-Duhem integration. UNIFAC subgroup assignment for toluene carries its own provenance (the curated groups.yaml has no toluene rows).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: unifac_fv supports exactly one solvent and one polymer; got 11 components (the polymer activity follows by Gibbs-Duhem integration)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
