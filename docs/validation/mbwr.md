# mbwr — Modified BWR-32 (Younglove-Ely 1987, pure C1/C2/C3)

family `helmholtz` · status **provisional** · adapter `ngdesign.thermo.bwr:MBWR32Package`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas
- polar: False · electrolyte: False
- T window: 90–600 K · P window: 1000–1e+08 Pa
- phases: V, L

## Parameters

- source: n/a
- provenance: n/a

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0 |
| phase_identification | ok | 0 | C1@160K ok; C3@300K ok |
| round_trip | ok | 2e-13 | 150K/2.5e+06Pa T_ph 2e-13 H 1.5e-13 T_ps 2e-13 |
| dhdT_cp | ok | 3.1e-07 | 300K/1e+06Pa vapor cp 36.7119 dH/dT 36.7119 |
| single_liquid_limit | ok | 0 | 150K/3e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 300K/5e+06Pa |

Note: In-house MBWR-32: Younglove-Ely units (rho mol/l, P MPa) at the kernel, SI at the boundary; ideal-gas reference as for bwrs. Mixtures are refused by the adapter. Saturation verified against CoolProp 8.0.0 across the ten bound cases (worst sampled Psat deviation about 0.4 %). All 96 Appendix-J coefficients digit-verified against the printed tables: the ethane G(3) entry was found mistranscribed and corrected (finite-difference and consistency tests had passed on the wrong value). One source caveat, not resolved in this work: selected Younglove-Ely isobar cross-checks (propane 250 K, methane 100 K) disagree by several percent for reasons not resolved here.

Declared exclusions (not silent skips):

- `gibbs_duhem` — MBWR-32 is pure-fluid only: the Younglove-Ely report gives no mixing rules for these coefficient tables, so the mixture Gibbs-Duhem gate cannot apply.

### L4 cross-model pairs

- n/a — refuses the slice feed: ComponentNotSupported: MBWR32Package has no parameters for component(s) ['C6+', 'CO2', 'H2O', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']; supported: ['C1', 'C2', 'C3']

## L1/L2 reference-case outcomes

105/105 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-C1-95.3K` — coolprop:CH4
- `pure-C1-125.0K` — coolprop:CH4
- `pure-C1-155.0K` — coolprop:CH4
- `pure-C1-181.0K` — coolprop:CH4
- `pure-C2-110.0K` — coolprop:C2H6
- `pure-C2-150.0K` — coolprop:C2H6
- `pure-C2-230.0K` — coolprop:C2H6
- `pure-C3-150.0K` — coolprop:C3H8
- `pure-C3-231.0K` — coolprop:C3H8
- `pure-C3-300.0K` — coolprop:C3H8

## References

- Younglove, B. A., Ely, J. F., 'Thermophysical Properties of Fluids. Part II: Methane, Ethane, Propane, Isobutane, and Normal Butane', J. Phys. Chem. Ref. Data 16, 577-798, 1987 - the 32-term pressure-form coefficients transcribed from Appendix J (NIST-hosted reprint), methane p. 794, ethane p. 795, propane p. 796
