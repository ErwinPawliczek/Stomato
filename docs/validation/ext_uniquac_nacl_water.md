# ext_uniquac_nacl_water — Extended UNIQUAC NaCl(aq) (registered refusal)

family `electrolyte` · status **experimental** · adapter `ngdesign.amine.electrolyte:ElectrolyteExtUNIQUAC`.

## Applicability

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: none — the row refuses at first use
- provenance: No openly retrievable, citable extended-UNIQUAC parameter table for NaCl-H2O exists (Thomsen & Rasmussen's fitted parameters are not published in citable open form). The T-07 precedent applies: the row refuses at first use rather than ship unverifiable parameters.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

The row refuses at first property use, so no L0 check can run; construction succeeds and every property call raises `NotImplementedError` naming the missing parameter table (pinned by tests/thermo/test_electrolyte.py).

## L1/L2 reference-case outcomes

None yet — the refusal stands until a verified citable parameter table lands in `data/thermo_params/electrolyte/`.

## References

- Thomsen, K. & Rasmussen, P., "Extended UNIQUAC for electrolyte systems" (parameters not openly retrievable; refusal documented, T-09)
