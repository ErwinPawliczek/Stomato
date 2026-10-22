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
| pure_psat_limit | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| phase_identification | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| round_trip | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| dhdT_cp | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| gibbs_duhem | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| single_liquid_limit | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| determinism | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: no verified saft_vr_mie parameters for ['C6+', 'CO2', 'H2O', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']; supported: ['C1', 'C2', 'C3'] (unsupported components are refused, never treated as ideal)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Lafitte, Apostolakis, Essmann & Muller, "Development of the truncated perturbed chain-polar SAFT... ", J. Chem. Phys. 139 (2013) 154504
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
