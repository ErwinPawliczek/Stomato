# pc_saft_assoc — PC-SAFT with association (registered refusal)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:PCSaftAssocThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, water, alcohol
- polar: True · electrolyte: False
- T window: 95–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: none — the row refuses to build
- provenance: teqp 0.23.2's PC-SAFT factory schema has no association-parameter fields, and no verified citable explicit PC-SAFT association parameter set is loaded in data/thermo_params/saft/pure.yaml; water/methanol association chemistry therefore stays outside the family instead of being silently dropped

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Declared exclusions (not silent skips):

- `determinism` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `dhdT_cp` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `gibbs_duhem` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `phase_identification` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `pure_psat_limit` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `round_trip` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)
- `single_liquid_limit` — row refuses to build — teqp's PC-SAFT has no association term (NotImplementedError in _build_kernel)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gross & Sadowski (2001), Ind. Eng. Chem. Res. 40, 1244-1257 (association term background)
