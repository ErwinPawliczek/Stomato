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

Note: Refusal row: EOS-CG stays unimplemented - the formulation is open (Gernert & Span 2016, J. Chem. Thermodyn. 93, 274-293), but the complete fluid parameter and departure-function tables ship only in the publisher's paywalled supplement, no open supplement was confirmed in the sources checked 2026-10-23, teqp does not ship EOS-CG fluid/departure files, and CoolProp issue #3277 requests exactly this missing support. What would change it: an openly redistributable parameter table or a licence that permits transcription of the full supplement.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Gernert, J., Span, R., 'EOS-CG: A Helmholtz energy mixture model for humid combustion gases', J. Chem. Thermodyn. 93, 274-293, 2016 (the formulation paper; the parameter tables live in its supplement, which is publisher-paywalled). no implementation in this repo; the row is a catalogue placeholder and every property call raises UnavailableBackend
