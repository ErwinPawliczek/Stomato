# polymer_nrtl — Chen segment-based polymer NRTL

family `special` · status **experimental** · adapter `ngdesign.thermo.special:ChenPolymerNRTLPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 10000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/polymer.yaml
- provenance: Chen (1993), Fluid Phase Equilibria 83, 301: segment combinatorial plus segment-level NRTL residual. Segment assignments and tau/alpha per segment pair with provenance; the shipped toluene/PS parameterization is an illustrative fit (no verified published parameter set located).

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
