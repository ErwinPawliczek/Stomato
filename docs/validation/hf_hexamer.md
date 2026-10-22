# hf_hexamer — HF-hexamerizing gamma-phi (in-house kernel, Jarry & Davis parameters)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:HFHexamerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 270–380 K · P window: 1000–500000 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house HF monomer-hexamer chemical-theory kernel: log10 Kp = a + b/T regressed from saturated-vapour densities by Jarry & Davis (J. Phys. Chem. 57, 600 (1953)), converted from their mmHg pressure basis to Pa. Schotte (Ind. Eng. Chem. Process Des. Dev. 19, 432 (1980)) is the oligomer-treatment reference for HF vapour association.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
