# T-15: Catalogue promotion sweep — turn provisional rows into validated ones

- **Phase:** Thermo catalogue, wave 4 (the freeze)
- **Depends on:** T-06, T-08, T-09, T-03b, #160, #164 merged
- **Packages you may edit:** `data/thermo_models/*.yaml` (status, validation, assessed), `data/validation/**` (new cases, corrected transcriptions with citations — never tolerances), `data/thermo_params/**` (replacement parameters with citations), `.github/workflows/ci.yml` only to add `--extra saft` to the backend and audit jobs if a teqp wheel installs on CI's Python, `docs/`
- **Contract change:** no (the `.github/` edit is orchestrator-applied)
- **Benchmark delta expected:** none

## Goal
The catalogue has ~140 rows with four `validated`. A row is `validated` only with L0–L3 green
(`docs/thermo-catalogue-plan.md` §3): L1 pure points and L2 binaries from literature with
citations, inside the fixed tolerances, with no fitted-to-case parameter standing in for an
independent check. This sweep does the data work that promotion needs and records, per row, why
a row stays `provisional` where it does.

## Work items (each a measured finding on the PR)
1. **MeOH/H2O 97.99 kPa series (#100):** re-transcribe the Bennett 1929 / DDB set 466 isobar from
   the primary source (or replace it with a cited modern isobar, e.g. Kurihara et al. 1993 at
   101.3 kPa); every gamma-phi and cubic case that references it is rebound; rows whose cases
   then pass are promoted.
2. **Morch dew points (#130):** confirm the Mørch et al. (2006) compositions and pressures against
   the paper; if the transcription holds, the cubic rows keep their declared misses and the
   `assessed:` notes cite the confirmation.
3. **Fitted-to-case rows (T-03 van Laar, Margules, UNIQUAC/Wilson MEG–H2O, MeOH–nC4):** bind one
   independent literature point per fitted pair (a different T or P from the fit point, cited);
   promote only the rows that pass it.
4. **SAFT rows:** if `uv sync --extra saft` installs on CI's Python (check for a teqp wheel), add
   the extra to the backend and audit jobs; run the pending SAFT cases in CI; promote
   `pc_saft` / `cpa_srk` / `multifluid` where L1+L2 pass.
5. **Kabadi–Danner:** bind a water/hydrocarbon mutual-solubility case (Kabadi & Danner 1985 or
   Tsonopoulos & Wilson 1983, cited); promote or declare.
6. **Lee–Kesler rows, Péneloux rows, K-value rows, Helmholtz pure rows:** bind the L1 points they
   lack; promote where green.
7. **Experimental rows that are genuine placeholders** (Helmholtz `asme_steam`, `eos_cg`,
   `aga8_dc92`, `mbwr`, `bwr_ls`; `twu-sim-tassone`; saft refusal rows): leave `experimental`,
   but the row's `l0_note` must say what would make it real (engine, parameters, licence) so the
   advisor can show it.
8. **Virial rows (T-03b, #172):** `nrtl_hoc` and `wilson_nothnagel` carry L1/L2 cases but stay
   `provisional` until item 1 settles the MeOH/H2O series (their only L2 misses are on it); add the
   HOC acetic-acid B(400 K) anchor from Hayden & O'Connell (1975) and the `hoc_dimer` vs `nrtl_hoc`
   acetic-acid vapour cross-check the T-03b spec asked for (two implementations of one physics must
   agree within 1 % or the discrepancy is explained, never widened); the 12 Nothnagel rows stay the
   declared Tsonopoulos-extended fallback unless the 1973 b/K table is found in a citable source.
9. **Electrolyte rows (T-09, #171):** the `enrtl_nacl_water` / `ext_uniquac_nacl_water` refusals are
   NOT promoted here (new adapters are out of scope; see the T-09b follow-up issue) — only their
   `l0_note` must name the published parameter sources (Chen & Evans 1986; Thomsen & Rasmussen 1999)
   so the advisor shows what would make them real.
10. Regenerate every report; `docs/validation.md` gets a status table (validated / provisional /
   experimental with the one-line reason per provisional row).

## Acceptance criteria
- [ ] Every row's status matches the audit rule; the number of `validated` rows is reported before/after
- [ ] No tolerance changed anywhere; every new or corrected case carries a citation
- [ ] CI green with the extra if it installs; otherwise the finding is recorded
- [ ] bench byte-identical; reports regenerated

## Out of scope
New adapters, new rows, unit operations.
