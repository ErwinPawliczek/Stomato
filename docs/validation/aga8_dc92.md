# aga8_dc92 — AGA 8 DC92 detail equation of state (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 143.15–676.48 K · P window: 100000–2.8e+08 Pa
- phases: V

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented. What would make it real: the AGA-8 DC92 detail-characterisation method, whose parameters live in the copyrighted AGA 1992 report (not redistributable) - needs a licensed copy or an in-house reimplementation from the published paper tables.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., Savidge, J. L., 'Compressibility Factors of Natural Gas and Other Related Hydrocarbon Gases', AGA Transmission Measurement Committee Report No. 8, 2nd ed., 1992 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
