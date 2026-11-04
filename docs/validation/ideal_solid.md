# ideal_solid — Ideal-solubility solid-liquid equilibrium

family `special` · status **provisional** · adapter `ngdesign.thermo.special:IdealSolidPackage`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 90–600 K · P window: 10000–1e+07 Pa
- phases: L

## Parameters

- source: chemicals databank fusion properties (Tm, Hfus by CAS), tabulated sources only
- provenance: van't Hoff ideal solubility ln x = -(dHfus/R)(1/T - 1/Tm), gamma = 1 (the ideal-solubility equation with the dCp terms neglected; Prausnitz, Lichtenthaler & de Azevedo, Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., solid-liquid equilibria chapter). Fusion properties from the chemicals databank: Tm from the first tabulated source chemicals ranks (Open Notebook melting points, CRC, CAS Common Chemistry, NIST WebBook, Wikidata), Hfus from the CRC Handbook table (chemicals method CRC); since 2026-11-03 the Joback group-contribution estimates are refused, so every number used is a tabulated value (naphthalene 353.35 K / 19010 J/mol, biphenyl 342.575 K / 18570 J/mol, anthracene 489.15 K / 29400 J/mol). Not a flash package: solubility(cid, T) is the surface, flash-style calls refuse.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

Note: The L0 checks are flash-surface checks and this row refuses every flash by design; its own self-consistency is pinned in tests/thermo/test_special.py instead - x(Tm) == 1 exactly, x rising with T, bit-identical instances, the closed form against a hand reduction, and the IUPAC-NIST published points.

Declared exclusions (not silent skips):

- `determinism` — flash_pt refuses by design; solubility(cid, T) is a closed form of tabulated constants (two instances agree bit-for-bit, pinned in tests/thermo/test_special.py)
- `dhdT_cp` — phase_props refuses by design (no phase enthalpy or Cp is claimed)
- `gibbs_duhem` — gamma = 1 by construction (ideal solubility), so the Gibbs-Duhem identity holds identically; there is no phase_props ln_phi to evaluate it on
- `phase_identification` — every flash-style entry point refuses by design (a solid-bearing stream must never be silently flashed as vapour/liquid); the SLE surface has no phase identification to check
- `pure_psat_limit` — not a VLE package - pure_psat returns None by contract (an SLE row contributes no vapour-pressure correlation); the surface is solubility(cid, T)
- `round_trip` — flash_pt/flash_ph refuse by design (SLE surface only)
- `single_liquid_limit` — flash_pt refuses by design (SLE surface only)

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ideal_solid is a solid-liquid equilibrium package and does not flash; use solubility(cid, T). A solid-bearing stream must be routed to the SLE surface, never silently flashed as vapor/liquid

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).
