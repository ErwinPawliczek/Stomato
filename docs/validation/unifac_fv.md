# unifac_fv — UNIFAC free-volume (Oishi-Prausnitz)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:UnifacFvPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 10000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/unifac_fv.yaml
- provenance: Oishi & Prausnitz, Ind. Eng. Chem. Process Des. Dev. 17, 333 (1978): UNIFAC solvent activity plus the Flory free-volume term (c1 = 1.1, 15.17 cm3/mol CH2 reference volume, b = 1.28); polymer activity by Gibbs-Duhem integration. UNIFAC residual from the original-UNIFAC tables shipped with thermo (UFSG/UFIP; Hansen et al., Ind. Eng. Chem. Res. 30, 2352 (1991)) at the flash temperature, on whole-molecule group fractions; van der Waals volumes r summed from the same UFSG R_k over the subgroup assignments (toluene: the DDBST assignment 5 ACH + ACCH3, r = 3.9228).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
