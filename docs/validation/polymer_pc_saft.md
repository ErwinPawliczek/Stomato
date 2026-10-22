# polymer_pc_saft — Polymer PC-SAFT (teqp bridge)

family `special` · status **experimental** · adapter `ngdesign.thermo.special:PolymerPCSAFT`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: False · electrolyte: False
- T window: 250–500 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/polymer.yaml (polymer_pc_saft section)
- provenance: PC-SAFT segment parameters for the polystyrene pseudo-component POLY_PS (AlHammadi & Abutaqiya, ACS Omega 5, 29530 (2020), Table 1, attributing Gross & Sadowski 2001) and the solvent toluene (Gross & Sadowski, Ind. Eng. Chem. Res. 40, 1244 (2001), Table 1; cross-checked against the feos-pcsaft project's literature parameter record). Builds through the T-07 teqp bridge (ngdesign.thermo.teqp_bridge); k_ij = 0 - no verifiable open citation for this pair's interaction parameter.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
