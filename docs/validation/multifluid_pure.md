# multifluid_pure — Multi-fluid Helmholtz, pure fluids (teqp CoolProp library)

family `saft` · status **provisional** · adapter `ngdesign.thermo.teqp_bridge:MultifluidPureThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp multifluid over the CoolProp fluid library (data/thermo_params/saft/pure.yaml alias table)
- provenance: same fluid data as the multifluid row; the row pins the pure-fluid surface (binary feeds are refused by design)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@150K bubble 0 dew 0; N2@90K bubble 0 dew 0; H2O@450K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@150K ok; H2O@450K ok |
| round_trip | ok | 5.1e-07 | 450K/3e+06Pa T_ph 1.5e-07 H 1.6e-07 T_ps 1.6e-07; 500K/1e+06Pa T_ph 1.5e-07 H 5.1e-07 T_ps 1.2e-07 |
| dhdT_cp | ok | 0 | 450K/200000Pa vapor cp 36.5279 dH/dT 36.5279 |
| single_liquid_limit | ok | 0 | 450K/3e+06Pa kinds=['aqueous'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 500K/1e+06Pa |

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure-fluid-only surface — binary feeds are refused by design, and the composition-loop check needs a binary; the family's mixture coverage runs on the multifluid row

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: multifluid_pure flashes pure fluids only; got ['C1', 'C2', 'C3', 'C6+', 'CO2', 'H2O', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

50/50 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-C1-95.3K` — coolprop:CH4
- `pure-C1-125.0K` — coolprop:CH4
- `pure-C1-155.0K` — coolprop:CH4
- `pure-C1-172.0K` — coolprop:CH4
- `pure-C1-181.0K` — coolprop:CH4
- `pure-CO2-216.7K` — coolprop:CO2
- `pure-CO2-240.0K` — coolprop:CO2
- `h2o-nist-273.179K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-347.390K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- `h2o-nist-401.605K` — NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21

## References

- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
