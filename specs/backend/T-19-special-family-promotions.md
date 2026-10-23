# T-19: Special family to provisional — ideal solid, Flory–Huggins, polymer NRTL, UNIFAC-FV, polymer PC-SAFT, HOC dimer, HF hexamer

- **Phase:** Thermo catalogue, post-freeze build-out of experimental rows
- **Depends on:** T-10, T-03b, T-15 (on main)
- **Packages you may edit:** `ngdesign.thermo.special`, `data/thermo_models/special.yaml`, `data/thermo_params/special/`, `data/validation/special/`, `docs/validation*`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none
- **GitHub issue:** #190

## Goal
All seven special rows run but have zero bound cases, and two carry illustrative or reduced parameters. Make each provisional with cited data.

## Steps
1. **ideal_solid:** solubility cases — naphthalene in benzene/toluene, anthracene, biphenyl (Prausnitz, Lichtenthaler & de Azevedo 3rd ed. ch. 11 tables or the original data papers). Assess the ideal-solubility miss honestly.
2. **flory_huggins / unifac_fv / polymer_pc_saft:** polystyrene/toluene and polystyrene/cyclohexane solvent activity (or weight-fraction activity coefficient) data from the original papers (e.g. Bawn et al. 1950, Krigbaum & Geymer 1959, or the papers the parameters already cite), bound to each row.
3. **polymer_nrtl:** the shipped parameters are an illustrative fit — replace with a published Chen 1993 (Fluid Phase Equilib. 83, 301) parameter set, or a parameter set from a paper using that model, with table citation; if none is open, keep the row experimental with the search documented.
4. **hoc_dimer:** acetic acid vapour apparent molar mass / compressibility vs published vapour-density data (e.g. Ritter & Simons 1945, or Mehling & Kleiber 2020 already cited); acetic acid/water VLE cases. The recorded B(400 K) gap stays recorded.
5. **hf_hexamer:** HF vapour compressibility vs Jarry & Davis 1953 / Long, Hildebrand & Morrell 1943 (cite tables).

## Rules (all T-16..T-19 threads)
- A row leaves `experimental` only when it builds, runs its L0 applicability sweep, and has at least one bound L1/L2 case from a cited independent source, with every miss in `assessed:` with measured numbers (T-15 discipline). Never widen a tolerance; never bind a case whose reference is the code under test.
- Every equation constant is checked against the cited table/equation number and the check is listed in the PR body (the 2026-10-22 lesson: LCVM, PSRK and Huron–Vidal had wrong constants that every finite-difference and consistency test passed). Add at least one closed-form or published-check-value test per row.
- Licences: never copy DIPPR, DECHEMA, Aspen, HYSYS, REFPROP or DWSIM (GPLv3) code or data. Public-domain US-government code (e.g. NIST) may be ported with citation. Parameters printed in a paper are facts and may be typed in with table/page citations.
- If a row cannot be made real from open sources, keep the refusal, rewrite its note with what exactly is missing (searched sources listed), and say so in the PR body — that is an acceptable outcome for one row, not for the whole spec.
- Regenerate `docs/validation*` with `scripts/validate_properties.py --write-doc`; `--audit` PASS; update `tests/thermo/test_catalogue.py` status counts; catalogue stays 137 rows.
