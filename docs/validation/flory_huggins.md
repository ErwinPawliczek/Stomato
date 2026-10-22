# flory_huggins — Flory-Huggins polymer solution

family `special` · status **experimental** · adapter `ngdesign.thermo.special:FloryHugginsPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 10000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/special/polymer.yaml
- provenance: Segment counts and chi per solvent/polymer pair with per-entry provenance; polystyrene/toluene chi = 0.67 at 435.46 K from Gunduz & Dincer, Polymer 21 (1980) 1131 (reduced from IGC infinite-dilution data). chi is the original composition- and temperature-independent FH form.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: flory_huggins supports exactly one solvent and one polymer; got 11 components (chi keys name the solvent first: 'solvent/polymer')

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
