# pc_saft_polar — Polar PC-SAFT (registered refusal)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:PCSaftPolarThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, acid_gas
- polar: True · electrolyte: False
- T window: 95–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: none — the row refuses to build
- provenance: teqp's PC-SAFT supports dipolar/quadrupolar coefficient fields, but no verified citable polar parameter set for the curated slate is loaded in data/thermo_params/saft/pure.yaml; unverified parameters are excluded rather than shipped (see pure.yaml `excluded:`)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Declared exclusions (not silent skips):

- `determinism` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `dhdT_cp` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `gibbs_duhem` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `phase_identification` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `pure_psat_limit` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `round_trip` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)
- `single_liquid_limit` — row refuses to build — no verified citable polar PC-SAFT parameter set (NotImplementedError in _build_kernel)

### L4 cross-model pairs

- n/a — refuses the slice feed: NotImplementedError: saft row 'pc_saft_polar' refuses to build: teqp (>= 0.15) ships a polar PC-SAFT extension, but no verified, citable component polar parameters ((Q*)^2, (mu*)^2) exist in data/thermo_params/saft/pure.yaml; parameter retrieval is out of T-07 scope

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gross & Vrabec, "An equation of state contribution for polar components: Dipolar molecules", AIChE J. 52 (2006) 1194-1204 (term background)
