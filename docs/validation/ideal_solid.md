# ideal_solid — Ideal-solubility solid-liquid equilibrium

family `special` · status **experimental** · adapter `ngdesign.thermo.special:IdealSolidPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 90–600 K · P window: 10000–1e+07 Pa
- phases: L

## Parameters

- source: chemicals databank fusion properties (Tm, Hfus by CAS)
- provenance: van't Hoff ideal solubility ln x = -(dHfus/R)(1/T - 1/Tm), gamma = 1. Fusion properties resolved from the chemicals databank at build time; a component without them refuses. Not a flash package: solubility(cid, T) is the surface, flash-style calls refuse.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ideal_solid is a solid-liquid equilibrium package and does not flash; use solubility(cid, T). A solid-bearing stream must be routed to the SLE surface, never silently flashed as vapor/liquid

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
