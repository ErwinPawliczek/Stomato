# enrtl_nacl_water — eNRTL NaCl(aq) -- REFUSED (no open parameter table)

family `electrolyte` · status **experimental** · adapter `ngdesign.amine.electrolyte:ElectrolyteENRTLNaCl`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: none -- first-use refusal
- provenance: No openly retrievable, citable eNRTL parameter table for NaCl-H2O exists (the published electrolyte-NRTL parameter sets for aqueous salts are not in citable open form, and DWSIM's electrolyte parameter files are not in the open repository).  The T-07 precedent applies: the row refuses at first use rather than ship unverifiable parameters.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: experimental row — L0 exempt; constructs successfully and refuses at first use (NotImplementedError) because no citable open eNRTL parameter table for NaCl-H2O exists (T-07 precedent)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
