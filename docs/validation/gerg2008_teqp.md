# gerg2008_teqp — GERG-2008 (teqp multi-fluid, exact parameters)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:Gerg2008TeqpThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp multifluid over teqp's bundled fluid library with the Kunz & Wagner (2012) GERG-2008 reducing/departure parameters (data/thermo_params/saft/pure.yaml gerg2008_teqp alias table)
- provenance: same teqp 0.23.2 bundled fluid library as the multifluid row; the natural-gas binary pairs and departure functions carry Kunz-JCED-2012 citations in teqp's mixture files. This row is the exact-backend cross-check the T-04 `gerg2008` row (CoolProp's fitted pure-fluid tables) defers to (issue

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

Declared case ids:

- `c1n2-130.079K-0.614MPa` — 

## References

- Kunz & Wagner, "The GERG-2008 Wide-Range Equation of State for Natural Gases and Other Mixtures", J. Chem. Eng. Data 57 (2012) 3032-3091
- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
