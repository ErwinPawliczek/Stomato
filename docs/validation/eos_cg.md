# eos_cg — EOS-CG combustion-gas mixture model (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: True · electrolyte: False
- T window: 90–2000 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented (teqp candidate, T-07). What would make it real: an in-house EOS-CG implementation from the open Kunz & Wagner 2012 formulation paper, or teqp multifluid support for its fluid files; no licence blocks it.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gernert, J., Span, R., 'EOS-CG: A Helmholtz energy mixture model for humid combustion gases', Chem. Eng. Sci. 148, 59-74, 2016 (no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend)
