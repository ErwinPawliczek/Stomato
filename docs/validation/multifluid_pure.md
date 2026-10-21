# multifluid_pure — Multi-fluid Helmholtz, pure fluids (teqp CoolProp library)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:MultifluidPureThermo`.

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
| pure_psat_limit | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| phase_identification | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| round_trip | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| dhdT_cp | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| single_liquid_limit | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |
| determinism | FAIL | n/a | raised SaftDependencyMissing: teqp is not installed; install the optional extra with `uv sync --extra saft` |

Declared exclusions (not silent skips):

- `gibbs_duhem` — pure-fluid-only surface — binary feeds are refused by design, and the composition-loop check needs a binary; the family's mixture coverage runs on the multifluid row

### L4 cross-model pairs

- n/a — refuses the slice feed: SaftParameterError: multifluid_pure flashes pure fluids only; got ['C1', 'C2', 'C3', 'C6+', 'CO2', 'H2O', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
