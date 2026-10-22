# mbwr — Modified BWR (Starling 1976, 27-compound set) (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas, water
- polar: True · electrolyte: False
- T window: 90–680 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented. What would make it real: an MBWR-32 engine plus the 32-coefficient sets from the open literature (Starling 1973 basis); refit targets on issue #167.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., Cox, K. W., Kwok, Y. C., et al., 'Modified BWR Equation of State Parameters for Twenty-Seven Compounds', ORO-5249-2 (U.S. ERDA report), Appendix B, 1976 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
