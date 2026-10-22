# ext_uniquac_nacl_water — Extended UNIQUAC NaCl(aq) -- REFUSED (no open parameter table)

family `electrolyte` · status **experimental** · adapter `ngdesign.amine.electrolyte:ElectrolyteExtUNIQUAC`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: none -- first-use refusal
- provenance: No openly retrievable, citable extended-UNIQUAC parameter table for NaCl-H2O exists (Thomsen & Rasmussen's fitted parameters are not published in citable open form).  The T-07 precedent applies: the row refuses at first use rather than ship unverifiable parameters.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: experimental row — L0 exempt; constructs successfully and refuses at first use (NotImplementedError) because no citable open extended-UNIQUAC parameter table for NaCl-H2O exists (T-07 precedent)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Thomsen, K. & Rasmussen, P., 'Extended UNIQUAC for electrolyte systems' (parameters not openly retrievable; refusal documented, T-09)
