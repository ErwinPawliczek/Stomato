# hoc_dimer — Dimerizing-acid gamma-phi (Hayden-O'Connell family, in-house kernel)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:HaydenOConnellDimerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 300–500 K · P window: 1000–2e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house dimerization chemical-theory kernel (Marek-Standart form, the leading association term of Hayden-O'Connell): Kp(T) from a reference dimerization constant and association enthalpy per component. Acetic-acid parameters reduced from Mehling & Kleiber (2020) J. Chem. Eng. Data / Ind. Eng. Chem. Res. acetic-acid vapour association data. The curated nrtl_hoc / nrtl_nothnagel rows keep their refusal (their wiring lives in ngdesign.thermo.gamma_phi, outside this spec's file list).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
