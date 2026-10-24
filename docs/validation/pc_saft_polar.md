# pc_saft_polar — Polar PC-SAFT (hand-rolled kernel)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:PCSaftPolarThermo`.

## Applicability (Carlson 1996)

- component classes: polar_organic
- polar: True · electrolyte: False
- T window: 230–520 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: hand-rolled PC-SAFT + Gross & Vrabec dipolar kernel, feos-curated G&V 2006 parameters (data/thermo_params/saft/pure.yaml)
- provenance: physical term (hard chain + dispersion) is the teqp-pinned reimplementation shared with pc_saft_assoc; dipolar term from Gross & Vrabec (2006) AIChE J. 52, 1194-1204 eqs. 8-14 (Padé [2/3]) with closed-form density and composition derivatives; the a/b/c universal coefficients typed from the feos source (feos-org/feos, BSD-3, 11 printed digits, retrieved 2026-10-23) and cross-checked digit by digit against teqp's and CoolProp's 7-digit constants (all 45 agree); the Debye-to-reduced-unit conversion is computed from exact SI constants (1e-19/kB = 7242.9705...) matching teqp/feos, not CoolProp's hardcoded 7242.7029... (37 ppm lower, inside the case bands); fluid parameters from feos's curated copy of the paper's Table 2 (gross2006.json — acetone and DME, both non-associating, one dipolar segment each); quadrupolar fluids (CO2, Gross 2005) stay unbound pending resolution of an open-source sign discrepancy in the J_QQQ,3ijk c0[0] constant; k_ij = 0 (the paper introduces no binary interaction parameter for the bound slate)

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

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

Declared case ids:

- `pure-ACETONE-296.0K-ps` — 
- `pure-ACETONE-350.0K-ps` — 
- `pure-ACETONE-400.0K-ps` — 
- `pure-ACETONE-450.0K-ps` — 
- `pure-DME-248.0K-ps` — 
- `pure-DME-280.0K-ps` — 
- `pure-DME-320.0K-ps` — 
- `pure-DME-360.0K-ps` — 

## References

- Gross & Vrabec, "An equation of state contribution for polar components: Dipolar molecules", AIChE J. 52 (2006) 1194-1204 (term background)
