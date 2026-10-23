# aga8_dc92 — AGA 8 DC92 detail equation of state (gas phase)

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.aga8:Aga8Dc92Package`.

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
| determinism | ok | 0 | two instances bit-identical at 350K/5e+06Pa |
| dhdT_cp | ok | 5.6e-07 | 350K/5e+06Pa vapor cp 41.0134 dH/dT 41.0134 |

Note: The declared checks exercise the gas surface the adapter offers (PT flash determinism, cp self-consistency); every excluded check exercises an operation the DC92 method structurally cannot provide, each refused with the typed Aga8Dc92Error.

Declared exclusions (not silent skips):

- `gibbs_duhem` — no fugacity coefficients - ln phi is not part of the DC92 surface
- `phase_identification` — the check anchors on the databank Psat, which pure_psat returns None for (no vapour-pressure correlation in the DC92 method)
- `pure_psat_limit` — gas-only method - no vapour-pressure correlation exists in DC92
- `round_trip` — the check iterates flash_ph/flash_ps, which the gas-only adapter refuses by design (no H/S-driven flashes are offered)
- `single_liquid_limit` — gas-only method - the adapter refuses liquid-phase requests

### L4 cross-model pairs

- n/a — refuses the slice feed: Aga8Dc92Error: AGA8 DC92 models gas only: no dew point

## L1/L2 reference-case outcomes

3/3 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `aga8-dc92-nist-check-gas-400K-50MPa` — Lemmon, Bell, Heinemann & Lu (2017) AGA8 Version 2.0 [Software], NIST, github.com/usnistgov/AGA8 @ 3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce, AGA8CODE/C Detail_test_01.cpp printed check values: 21-component example gas at 400 K / 50 000 kPa - molar density 12.80792403648801 mol/l, molar mass 20.54333051 g/mol, Z 1.173801364147326, cp 58.54617672380667 J/(mol K); retrieved 2026-10-21

## References

- Starling, K. E., Savidge, J. L., 'Compressibility Factors of Natural Gas and Other Related Hydrocarbon Gases', AGA Transmission Measurement Committee Report No. 8, 2nd ed., 1992 (coefficients as published in NIST''s public-domain reference implementation, github.com/usnistgov/AGA8 @ 3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce, AGA8CODE/C, retrieved 2026-10; the port reproduces Detail_test_01.cpp check values)
