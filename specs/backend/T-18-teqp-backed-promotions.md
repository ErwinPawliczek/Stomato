# T-18: teqp-backed rows to provisional — SAFT-VR Mie, multifluid, multifluid pure, GERG-2008 (teqp)

- **Phase:** Thermo catalogue, post-freeze build-out of experimental rows
- **Depends on:** T-07, T-15c, CI `--extra saft` (#178, on main)
- **Packages you may edit:** `ngdesign.thermo.teqp_bridge`, `data/thermo_models/saft.yaml` (these four rows), `data/thermo_params/saft/`, `data/validation/`, `docs/validation*`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** #188

## Goal
These four rows build and run but have no bound cases. Bind and measure them.

## Steps
1. **Licensing ruling (orchestrator, 2026-10-23):** the multi-fluid rows use the fluid library shipped inside the installed teqp wheel at runtime; the repository never copies, vendors or regenerates those fluid files. That is allowed; the T-15c note saying "not redistributable" is replaced with this ruling.
2. Bind L1/L2 cases from the cases already in `data/validation/` that fall inside each row's applicability (natural-gas densities, C1/C3, C1/CO2, C1/N2 VLE, pure-fluid NIST points). gerg2008_teqp: GERG-2008 check values from Kunz & Wagner 2012 Table A2.x (cite) plus the existing cases; it must agree with the CoolProp `gerg2008` row within the published uncertainty.
3. saft_vr_mie: Lafitte 2013 parameters are already loaded; bind the alkane cases; add CO2 and N2 only with parameters from a cited table.
4. multifluid_pure: bind the pure-fluid saturation/density cases; multifluid: binary cases, refusing water-bearing feeds as today.
5. Measure every case, assess every miss, promote what the rules allow.

## Rules (all T-16..T-19 threads)
- A row leaves `experimental` only when it builds, runs its L0 applicability sweep, and has at least one bound L1/L2 case from a cited independent source, with every miss in `assessed:` with measured numbers (T-15 discipline). Never widen a tolerance; never bind a case whose reference is the code under test.
- Every equation constant is checked against the cited table/equation number and the check is listed in the PR body (the 2026-10-22 lesson: LCVM, PSRK and Huron–Vidal had wrong constants that every finite-difference and consistency test passed). Add at least one closed-form or published-check-value test per row.
- Licences: never copy DIPPR, DECHEMA, Aspen, HYSYS, REFPROP or DWSIM (GPLv3) code or data. Public-domain US-government code (e.g. NIST) may be ported with citation. Parameters printed in a paper are facts and may be typed in with table/page citations.
- If a row cannot be made real from open sources, keep the refusal, rewrite its note with what exactly is missing (searched sources listed), and say so in the PR body — that is an acceptable outcome for one row, not for the whole spec.
- Regenerate `docs/validation*` with `scripts/validate_properties.py --write-doc`; `--audit` PASS; update `tests/thermo/test_catalogue.py` status counts; catalogue stays 137 rows.
