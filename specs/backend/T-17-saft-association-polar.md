# T-17: SAFT family, association and polar — PC-SAFT assoc, polar PC-SAFT, CPA-PR, soft-SAFT

- **Phase:** Thermo catalogue, post-freeze build-out of experimental rows
- **Depends on:** T-07, T-15c (cpa_srk hand-rolled association, on main)
- **Packages you may edit:** `ngdesign.thermo` (new `saft_assoc.py`; reuse — do not fork — the association solver behind `cpa_srk`, moving it into `saft_assoc.py` if it is private to another module), `data/thermo_models/saft.yaml` (these four rows), `data/thermo_params/saft/`, `data/validation/saft/`, `docs/validation*`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** #191

## Goal
The four SAFT rows that refuse because the engine or verified parameters were missing. T-18 edits `teqp_bridge.py` concurrently: put your code in `saft_assoc.py` and repoint these rows' adapters there; do not edit `teqp_bridge.py` except to import from `saft_assoc.py`.

## Steps (post a checkpoint with numbers after each)
1. **One Wertheim TPT1 association term** (site fractions solved once, Michelsen & Hendriks 2001 formulation; schemes 2B/3B/4C per Huang & Radosz 1990) shared by cpa_srk (unchanged numbers — its bound cases must stay byte-identical) and the new rows.
2. **cpa_pr:** PR physical term + the step-1 association term; parameters from a cited CPA-PR paper (search; e.g. the Kontogeorgis/Folas or Tsivintzelis literature). Water saturation and methanol/water VLE cases.
3. **pc_saft_assoc:** PC-SAFT (teqp or the existing kernel for the hard-chain/dispersion parts) + the association term with Gross & Sadowski 2002 (Ind. Eng. Chem. Res. 41, 5510) parameters for water/methanol/ethanol; validate water ρ_L and Psat and MeOH/H2O VLE.
4. **pc_saft_polar:** Gross & Vrabec 2006 (AIChE J. 52, 1194) dipolar term with their published parameters (teqp exposes the polar fields — check its implementation matches the paper's constants a/b/c tables before trusting it); validate e.g. acetone/DME/CO2 (quadrupolar, Gross 2005) points.
5. **soft_saft:** only after 1–4. Blas & Vega 1997 with the Johnson, Zollweg & Gubbins (1993) LJ reference EOS — 33-parameter MBWR for LJ, constants checked against the paper's table. If it does not fit in the thread, leave it refusing with the state documented.

## Rules (all T-16..T-19 threads)
- A row leaves `experimental` only when it builds, runs its L0 applicability sweep, and has at least one bound L1/L2 case from a cited independent source, with every miss in `assessed:` with measured numbers (T-15 discipline). Never widen a tolerance; never bind a case whose reference is the code under test.
- Every equation constant is checked against the cited table/equation number and the check is listed in the PR body (the 2026-10-22 lesson: LCVM, PSRK and Huron–Vidal had wrong constants that every finite-difference and consistency test passed). Add at least one closed-form or published-check-value test per row.
- Licences: never copy DIPPR, DECHEMA, Aspen, HYSYS, REFPROP or DWSIM (GPLv3) code or data. Public-domain US-government code (e.g. NIST) may be ported with citation. Parameters printed in a paper are facts and may be typed in with table/page citations.
- If a row cannot be made real from open sources, keep the refusal, rewrite its note with what exactly is missing (searched sources listed), and say so in the PR body — that is an acceptable outcome for one row, not for the whole spec.
- Regenerate `docs/validation*` with `scripts/validate_properties.py --write-doc`; `--audit` PASS; update `tests/thermo/test_catalogue.py` status counts; catalogue stays 137 rows.
