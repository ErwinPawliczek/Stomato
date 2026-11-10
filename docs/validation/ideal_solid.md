# ideal_solid — Ideal-solubility solid-liquid equilibrium

family `special` · status **validated** · adapter `ngdesign.thermo.special:IdealSolidPackage`.

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

15/16 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `sle-pure-naphthalene-tfus-nist` — NIST Chemistry WebBook, NIST Standard Reference Database 69 (Linstrom & Mallard eds.), naphthalene, Phase change data table, T fus = 353.2 +/- 0.7 K (average of 55 of 57 values), AVG; https://webbook.nist.gov/cgi/cbook.cgi?ID=C91203&Mask=4, retrieved 2026-11-04.
- `sle-pure-biphenyl-tfus-nist` — NIST Chemistry WebBook, NIST Standard Reference Database 69 (Linstrom & Mallard eds.), biphenyl, Phase change data table, T fus = 343. +/- 1. K (average of 285 of 294 values), AVG; https://webbook.nist.gov/cgi/cbook.cgi?ID=C92524&Mask=4, retrieved 2026-11-04.
- `sle-pure-anthracene-tfus-nist` — NIST Chemistry WebBook, NIST Standard Reference Database 69 (Linstrom & Mallard eds.), anthracene, Phase change data table, T fus = 490. +/- 3. K (average of 27 values), AVG; https://webbook.nist.gov/cgi/cbook.cgi?ID=C120127&Mask=4, retrieved 2026-11-04.
- `sle-naphthalene-benzene-298.15K-chang` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_123, Naphthalene with Benzene, Experimental Data table (t = 25.0 C, solute mole fraction x1 = 0.292), compiled by W.E. Acree Jr. from Chang, W., Ph.D. Dissertation, North Dakota State University (1969); retrieved 2026-11-04. Estimated error x1 +/- 2 % (compiler).
- `sle-naphthalene-benzene-273.2K-ward` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_125, Naphthalene with Benzene, Experimental Data table row T/K = 273.2, x1 = 0.151, compiled by W.E. Acree Jr. from Ward, H.L., J. Phys. Chem. 30, 1316-1333 (1926); retrieved 2026-11-04. Every fourth row of the 17-row table (rows 1, 5, 9, 13, 17), chosen by position before the model was run.
- `sle-naphthalene-benzene-282.2K-ward` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_125, Naphthalene with Benzene, Experimental Data table row T/K = 282.2, x1 = 0.19, compiled by W.E. Acree Jr. from Ward, H.L., J. Phys. Chem. 30, 1316-1333 (1926); retrieved 2026-11-04. Every fourth row of the 17-row table (rows 1, 5, 9, 13, 17), chosen by position before the model was run.
- `sle-naphthalene-benzene-303.3K-ward` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_125, Naphthalene with Benzene, Experimental Data table row T/K = 303.3, x1 = 0.333, compiled by W.E. Acree Jr. from Ward, H.L., J. Phys. Chem. 30, 1316-1333 (1926); retrieved 2026-11-04. Every fourth row of the 17-row table (rows 1, 5, 9, 13, 17), chosen by position before the model was run.
- `sle-naphthalene-benzene-321.1K-ward` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_125, Naphthalene with Benzene, Experimental Data table row T/K = 321.1, x1 = 0.516, compiled by W.E. Acree Jr. from Ward, H.L., J. Phys. Chem. 30, 1316-1333 (1926); retrieved 2026-11-04. Every fourth row of the 17-row table (rows 1, 5, 9, 13, 17), chosen by position before the model was run.
- `sle-naphthalene-benzene-343.5K-ward` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_125, Naphthalene with Benzene, Experimental Data table row T/K = 343.5, x1 = 0.833, compiled by W.E. Acree Jr. from Ward, H.L., J. Phys. Chem. 30, 1316-1333 (1926); retrieved 2026-11-04. Every fourth row of the 17-row table (rows 1, 5, 9, 13, 17), chosen by position before the model was run.
- `sle-naphthalene-benzene-308.2K-mclaughlin` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_124, Naphthalene with Benzene, Experimental Data table row T/K = 308.2, x1 = 0.3766, compiled by W.E. Acree Jr. from McLaughlin, E.; Zainal, H.A., J. Chem. Soc. 1959, 863-867; retrieved 2026-11-04. All five rows of the table are bound.
- `sle-naphthalene-benzene-318.2K-mclaughlin` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_124, Naphthalene with Benzene, Experimental Data table row T/K = 318.2, x1 = 0.4806, compiled by W.E. Acree Jr. from McLaughlin, E.; Zainal, H.A., J. Chem. Soc. 1959, 863-867; retrieved 2026-11-04. All five rows of the table are bound.
- `sle-naphthalene-benzene-320.6K-mclaughlin` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_124, Naphthalene with Benzene, Experimental Data table row T/K = 320.6, x1 = 0.5094, compiled by W.E. Acree Jr. from McLaughlin, E.; Zainal, H.A., J. Chem. Soc. 1959, 863-867; retrieved 2026-11-04. All five rows of the table are bound.
- `sle-naphthalene-benzene-336.4K-mclaughlin` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_124, Naphthalene with Benzene, Experimental Data table row T/K = 336.4, x1 = 0.7119, compiled by W.E. Acree Jr. from McLaughlin, E.; Zainal, H.A., J. Chem. Soc. 1959, 863-867; retrieved 2026-11-04. All five rows of the table are bound.
- `sle-naphthalene-benzene-349.0K-mclaughlin` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=59_124, Naphthalene with Benzene, Experimental Data table row T/K = 349.0, x1 = 0.918, compiled by W.E. Acree Jr. from McLaughlin, E.; Zainal, H.A., J. Chem. Soc. 1959, 863-867; retrieved 2026-11-04. All five rows of the table are bound.
- `sle-biphenyl-benzene-298.15K-chang` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=58_241, Biphenyl with Benzene, critical evaluation by W.E. Acree Jr. (1994): experimental value x1 = 0.381 at 298 K from Chang, W., Ph.D. Dissertation, North Dakota State University (1969) (Critical Evaluation paragraph, ref. 4; the evaluated regression of the page's Fig. 1, ln x1 = -2233.1/T + 6.5272 back-calculates 0.3819); retrieved 2026-11-04.
- `sle-anthracene-benzene-298.15K-acree` — IUPAC-NIST Solubility Database (NIST Standard Reference Database 106), https://srdata.nist.gov/solubility/sol_detail.aspx?sysID=58_57, Anthracene with Benzene, critical evaluation by W.E. Acree Jr. (1994): evaluated ln x1 = -3200.1/T + 5.7899, back-calculated x1 = 0.00713 at 298 K (experimental 0.00711 Smutek et al. 1967, 0.007418 Acree & Rytting 1983, 0.00740 Mahieu 1936; Critical Evaluation paragraph, regression shown in the page's Fig. 1); retrieved 2026-11-04.
