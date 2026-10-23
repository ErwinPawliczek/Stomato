# aga8_dc92 — AGA 8 DC92 detail equation of state (direct module; adapter placeholder)

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

Note: Direct module validated against the NIST printed check values; the catalogue adapter stays a placeholder because the validation harness is saturation-shaped and cannot express gas-only cases (experimental rows skip bound cases, provisional rows must run them) - the harness would need a gas-only case type before this row can promote.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Starling, K. E., Savidge, J. L., 'Compressibility Factors of Natural Gas and Other Related Hydrocarbon Gases', AGA Transmission Measurement Committee Report No. 8, 2nd ed., 1992 (coefficients as published in NIST''s public-domain reference implementation, github.com/usnistgov/AGA8 @ 3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce, AGA8CODE/C, retrieved 2026-10; the port reproduces Detail_test_01.cpp check values)
