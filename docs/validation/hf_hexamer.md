# hf_hexamer — HF-hexamerizing gamma-phi (in-house kernel, Jarry & Davis parameters)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:HFHexamerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 270–380 K · P window: 1000–500000 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house chemical-theory vapour, the hoc_dimer construction with the monomer-hexamer equilibrium 6 HF <=> (HF)6 (special.AssociatingGas with n = 6): log10 Kp = a + b/T regressed from saturated-vapour densities by Jarry & Davis (J. Phys. Chem. 57, 600 (1953)), converted from their mmHg pressure basis to Pa; association enthalpy -R b ln10 = -165.8 kJ per mole of hexamer. Schotte (Ind. Eng. Chem. Process Des. Dev. 19, 432 (1980)) is the oligomer-treatment reference for HF vapour association. Liquid ideal on apparent composition with HF's saturation fugacity coefficient (PhiSat basis).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
