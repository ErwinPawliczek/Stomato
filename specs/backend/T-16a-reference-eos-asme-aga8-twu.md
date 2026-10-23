# T-16a: Reference equations, part 1 — ASME steam (IF97 basis, fixes #177), AGA8 DC92, Twu–Sim–Tassone

- **Phase:** Thermo catalogue, post-freeze build-out of experimental rows
- **Depends on:** T-04, T-15 (on main)
- **Packages you may edit:** `ngdesign.thermo` (`helmholtz.py` IF97/ASME parts only, new `aga8.py`, `cubic.py` Twu–Sim–Tassone parts only), `data/thermo_models/{helmholtz,cubic}.yaml` (these three rows + the IF97 row), `data/thermo_params/helmholtz/`, `data/validation/`, `docs/validation*`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** #187 (also fixes #177)

## Goal
Turn three experimental rows real.

## Steps
1. **#177 first:** the IAPWS-IF97 adapter returns saturated liquid/vapour densities label-swapped at saturation states. Fix at the phase-labelling owner, add a test at three saturation states vs IAPWS-IF97 Tables (cite table), re-measure the IF97 row.
2. **asme_steam:** the current ASME Steam Tables (7th ed., 2000 onward) are computed from IAPWS-IF97. Make the row an honest IF97-based ASME-labelled package over the same kernel (no duplicate code), applicability per the ASME tables, and bind the IF97 verification values (IAPWS R7-97 check tables) as its L1 cases. Note the historical 1967 IFC formulation is not implemented.
3. **aga8_dc92:** implement the AGA Report No. 8 (1992/1994) detail characterisation method in `thermo/aga8.py`, porting from NIST's public-domain AGA8 reference code (usnistgov/AGA8, cite commit) — gas-phase Z, density and derived properties; refuse liquid/two-phase states and components outside the 21 AGA8 species. Validate against the report's published check values for its example gases (cite table) to their printed digits.
4. **twu-sim-tassone:** it has 9 bound cases and L1=0. Diagnose (measured: each case's numbers), fix any constant/sign error against Twu, Sim & Tassone (2002) Fluid Phase Equilib. 194–197, 1023 (the constants in the row: a_c 0.470507, b 0.0740740, v²+2.5bv−1.5b²), then promote per the rules.

## Rules (all T-16..T-19 threads)
- A row leaves `experimental` only when it builds, runs its L0 applicability sweep, and has at least one bound L1/L2 case from a cited independent source, with every miss in `assessed:` with measured numbers (T-15 discipline). Never widen a tolerance; never bind a case whose reference is the code under test.
- Every equation constant is checked against the cited table/equation number and the check is listed in the PR body (the 2026-10-22 lesson: LCVM, PSRK and Huron–Vidal had wrong constants that every finite-difference and consistency test passed). Add at least one closed-form or published-check-value test per row.
- Licences: never copy DIPPR, DECHEMA, Aspen, HYSYS, REFPROP or DWSIM (GPLv3) code or data. Public-domain US-government code (e.g. NIST) may be ported with citation. Parameters printed in a paper are facts and may be typed in with table/page citations.
- If a row cannot be made real from open sources, keep the refusal, rewrite its note with what exactly is missing (searched sources listed), and say so in the PR body — that is an acceptable outcome for one row, not for the whole spec.
- Regenerate `docs/validation*` with `scripts/validate_properties.py --write-doc`; `--audit` PASS; update `tests/thermo/test_catalogue.py` status counts; catalogue stays 137 rows.
