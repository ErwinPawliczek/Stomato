# saft_vr_mie — SAFT-VR Mie (teqp)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:SaftVrMieThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon
- polar: False · electrolyte: False
- T window: 90–420 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp SAFT-VR-Mie, explicit coefficients (data/thermo_params/saft/pure.yaml)
- provenance: m, sigma, lambda_r, lambda_a from Lafitte, Apostolakis, Essmann & Muller (2013) J. Chem. Phys. 139, 154504 (DOI 10.1063/1.4819786), cross-checked against teqp 0.23.2's compiled parameter values to printed precision (methane, ethane, propane); k_ij = 0 for the pairs in scope

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Lafitte, Apostolakis, Essmann & Muller, "Development of the truncated perturbed chain-polar SAFT... ", J. Chem. Phys. 139 (2013) 154504
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
