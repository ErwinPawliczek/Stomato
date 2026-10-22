# soft_saft — soft-SAFT (registered refusal)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:SoftSaftThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas
- polar: False · electrolyte: False
- T window: 95–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: none — the row refuses to build
- provenance: Blas & Vega's (1997) soft-SAFT has no engine to run on — teqp 0.23.2 (the family's only optional backend) ships no soft-SAFT kernel (its SAFT factories are the explicit-coefficient PC-SAFT and SAFT-VR-Mie engines), and writing SAFT by hand is out of T-07 scope; the model therefore stays outside the family rather than being approximated

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Declared exclusions (not silent skips):

- `determinism` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `dhdT_cp` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `gibbs_duhem` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `phase_identification` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `pure_psat_limit` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `round_trip` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)
- `single_liquid_limit` — row refuses to build — no soft-SAFT engine exists (measured — teqp 0.23.2 has no soft-SAFT factory or teqp.saft module)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Blas & Vega, "Prediction of binary and multicomponent vapor-liquid equilibria with the soft-SAFT equation of state" (association-free soft-SAFT formulation), Ind. Eng. Chem. Res. 37 (1998) 660-674; vega group soft-SAFT lineage
