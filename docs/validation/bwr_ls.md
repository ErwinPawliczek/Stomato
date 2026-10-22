# bwr_ls — BWR-Lee-Starling (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 95–600 K · P window: 1000–7e+07 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented. What would make it real: a BWR-Lee-Starling engine with the Lee-Starling coefficient tables transcribed from the open papers.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Lee, B. I., Starling, K. E., Starling's BWR equation variant as summarized in 'Thermodynamic Property Prediction of Light Hydrocarbons and Related Fluids' (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
