# cpa_pr — CPA-PR (registered refusal)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:CpaPrThermo`.

## Applicability (Carlson 1996)

- component classes: water, alcohol, glycol
- polar: True · electrolyte: False
- T window: 250–620 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: none — the row refuses to build
- provenance: teqp 0.23.2's CPA engine NaNs its fugacity coefficients at liquid-like densities and collapses the water saturation line with the published Kontogeorgis parameters (measured in the T-07 exploration); a Peng-Robinson CPA variant would need the same hand-rolled treatment as cpa_srk and no verified citable CPA-PR parameter set is loaded for the slate

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Declared exclusions (not silent skips):

- `determinism` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `dhdT_cp` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `gibbs_duhem` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `phase_identification` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `pure_psat_limit` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `round_trip` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)
- `single_liquid_limit` — row refuses to build — teqp's CPA is unusable (fugacity NaNs at liquid-like density; NotImplementedError in _build_kernel)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Kontogeorgis, Voutsas, Yakoumis & Tassios, Ind. Eng. Chem. Res. 35 (1996) 4631-4642
