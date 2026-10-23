# hoc_dimer — Dimerizing-acid gamma-phi (Hayden-O'Connell family, in-house kernel)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:HaydenOConnellDimerPackage`.

## Applicability (Carlson 1996)

- component classes: polar_organic, acid_gas
- polar: True · electrolyte: False
- T window: 300–500 K · P window: 1000–2e+06 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/association.yaml
- provenance: In-house dimerization chemical-theory kernel (Marek-Standart form, the leading association term of Hayden-O'Connell): Kp(T) from a reference dimerization constant and association enthalpy per component. Acetic-acid parameters from Ritter & Simons (1945): log10 K2 = 3164/T - 10.4184 (mmHg^-1), dH = -3164 R ln10 = -60.57 kJ/mol (verified via Sebastiani & Lacquaniti, Chem. Eng. Sci. 22, 1155 (1967); data/thermo_params/special/association.yaml). Independent prediction vs Mehling & Kleiber (2020) measured Z = 0.6299 at 399.35 K, 1 bar true: +3.8% miss, assessed in tests/thermo/test_special.py. The curated nrtl_hoc / nrtl_nothnagel rows keep their refusal (their wiring lives in ngdesign.thermo.gamma_phi, outside this spec's file list).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
