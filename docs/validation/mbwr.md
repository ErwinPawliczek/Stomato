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

Note: Placeholder row: the method is recorded, not implemented.

### L4 cross-model pairs

- n/a — refuses the slice feed: UnavailableBackend: helmholtz-family placeholder row has no dew_point implementation; the backend lands with a later spec (teqp bridge, T-07)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., Cox, K. W., Kwok, Y. C., et al., 'Modified BWR Equation of State Parameters for Twenty-Seven Compounds', ORO-5249-2 (U.S. ERDA report), Appendix B, 1976 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
