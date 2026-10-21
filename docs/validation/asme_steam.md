# asme_steam — ASME/NBS steam tables (placeholder)

family `helmholtz` · status **experimental** · adapter `ngdesign.thermo.helmholtz:UnavailablePackage`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: False
- T window: 273.15–1073.15 K · P window: 500–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: Placeholder row: the method is recorded, not implemented. The IAPWS-95 and IF97 rows carry the real steam-table evaluations.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- ASME Steam Tables (ASME Performance Test Codes; the historical ASME/NBS formulation has no implementation in this repo - the row is a catalogue placeholder and every property call raises UnavailableBackend)
