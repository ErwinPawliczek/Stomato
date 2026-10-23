# T-16b: Reference equations, part 2 — MBWR (Starling 27-compound), BWR-Lee-Starling, EOS-CG

- **Phase:** Thermo catalogue, post-freeze build-out of experimental rows
- **Depends on:** T-04, T-07, T-15 (on main)
- **Packages you may edit:** `ngdesign.thermo` (new `bwr.py`, new `eos_cg.py`; `helmholtz.py` only to repoint these rows' adapters), `data/thermo_models/helmholtz.yaml` (these three rows), `data/thermo_params/helmholtz/`, `data/validation/`, `docs/validation*`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** #194

## Goal
Turn the three remaining Helmholtz-family placeholders real. T-16a works in `helmholtz.py` IF97 parts and `aga8.py` concurrently — stay in your own modules.

## Steps
1. **bwr_ls:** the Benedict–Webb–Rubin–Starling equation with the Han–Starling generalised parameters (Starling 1973, *Fluid Thermodynamic Properties for Light Petroleum Systems*; Han & Starling 1972) in `thermo/bwr.py`: pure and mixture (Starling mixing rules with k_ij from the same source), PT flash through the existing flash machinery used by the other Helmholtz/BWR adapters. Validate methane/ethane/propane densities and a C1/C3 VLE point against cited data already in `data/validation/` where possible.
2. **mbwr:** the 32-term MBWR with the Starling et al. 1976 (ORO-5249-2, a public US ERDA report) coefficients for the compounds you can source and cite page-by-page; pure fluids first, mixtures only if the report gives the rules. Refuse uncovered compounds by name.
3. **eos_cg:** Gernert & Span (2016) Chem. Eng. Sci. 148, 59 — implement only if the full pure-fluid references and binary departure parameters are printed in the paper/supplement; prefer driving teqp's multifluid engine with a JSON built from the printed parameters over hand-coding. Validate against the paper's check values. If the parameter set is not openly obtainable, keep the refusal per the rules.

## Rules (all T-16..T-19 threads)
- A row leaves `experimental` only when it builds, runs its L0 applicability sweep, and has at least one bound L1/L2 case from a cited independent source, with every miss in `assessed:` with measured numbers (T-15 discipline). Never widen a tolerance; never bind a case whose reference is the code under test.
- Every equation constant is checked against the cited table/equation number and the check is listed in the PR body (the 2026-10-22 lesson: LCVM, PSRK and Huron–Vidal had wrong constants that every finite-difference and consistency test passed). Add at least one closed-form or published-check-value test per row.
- Licences: never copy DIPPR, DECHEMA, Aspen, HYSYS, REFPROP or DWSIM (GPLv3) code or data. Public-domain US-government code (e.g. NIST) may be ported with citation. Parameters printed in a paper are facts and may be typed in with table/page citations.
- If a row cannot be made real from open sources, keep the refusal, rewrite its note with what exactly is missing (searched sources listed), and say so in the PR body — that is an acceptable outcome for one row, not for the whole spec.
- Regenerate `docs/validation*` with `scripts/validate_properties.py --write-doc`; `--audit` PASS; update `tests/thermo/test_catalogue.py` status counts; catalogue stays 137 rows.
