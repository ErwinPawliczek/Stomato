# Stomato agent board

Shared coordination file for all agents working on Stomato. Read `agents/PROTOCOL.md` first.
Times are America/Chicago (CST). Newest handoff on top.

## Task board

| id | title | owner | status | branch | updated |
|----|-------|-------|--------|--------|---------|
| V1 | Validation run: cite reference cases for provisional thermo models, then R2 units | Claude Code | in progress (resumed 11:35 AM after usage reset; val-infra merged into chem-engine 11:35) | chem-engine (local run, log `~/stomato-val.log`) | 2026-11-04 11:45 AM |
| T1 | Obvious trial (superseded by T1r) | Obvious | dropped (stale since 10:50 AM, nothing pushed) | — | 2026-11-04 12:15 PM |
| T1r | Retry T1 with push rules: data pack PR ethane/propane VLE + NRTL ethanol/water VLE (IF97 dropped: V1 validated it) | Obvious | claimed | obv/T1r | 2026-11-04 12:07 PM |
| T3 | SR-POLAR: find open published RKUPP p1-p3 parameters + c_i(T) translation and a worked example | Obvious | claimed | obv/T3 | 2026-11-04 12:06 PM |
| T4 | API liquid density: public reproductions of API TDB 6A3.5 / Rackett-type petroleum correlations with worked examples | Obvious | review | obv/T4 | 2026-11-04 12:11 PM |
| T5 | COSMO-SAC: open sigma-profile DBs (VT-2005, UD/NIST Bell 2020) + independent gamma-inf/VLE pack | Obvious | claimed | obv/T5 | 2026-11-04 12:07 PM |
| T6 | Polymer SRK / polymer-solvent: open polymer-solvent VLE data independent of Kiss 2009 | Obvious | claimed | obv/T6 | 2026-11-04 12:06 PM |
| T7 | Acetic acid/water open VLE pack (hoc_dimer L2 gap) | Obvious | review | obv/T7 | 2026-11-04 12:12 PM |
| T8 | Bring reformer_cat.yaml (PR #329) + control_valve.yaml (PR #282) case files into a chem-engine PR | Obvious | claimed | obv/T8 | 2026-11-04 1:20 PM |
| T2 | Board loop test | Obvious | done | agents-board | 2026-11-04 10:57 AM |

Status values: `open`, `claimed`, `in progress`, `blocked`, `review`, `done`, `dropped`.

## Handoffs

### T7 — Obvious — 2026-11-04 12:12 PM
- Done: Acetic acid/water open VLE pack for `hoc_dimer` assembled from three open sources retrieved this session; PR open into `chem-engine`.
- Outputs (paths / branch / commit / PR #): `data/validation/packs/T7/{data.csv,pack.yaml}` on branch `obv/T7`, commit e6b7a58; **PR #339** (obv/T7 → chem-engine): https://github.com/ErwinPawliczek/Stomato/pull/339. 79 cited data rows; 75 cases (23 isobaric binary T,x,y + 44 isothermal binary T,P,x + 8 pure-AcOH Psat cases: 6 Antoine evaluations labelled computed + 2 measured anchors). Tolerances per P1-05 (bubble_T 0.5 %, y 0.02 abs, bubble_P 3 %).
- Sources used: (1) Sebastiani & Lacquaniti, Chem. Eng. Sci. 22 (1967) 1155-1162, DOI 10.1016/0009-2509(67)80182-9, Table 1 p. 1157 — 23 isobaric points at atmospheric pressure (open PDF, retrieved 2026-11-04); (2) Román-Ramírez & Leeke, J. Chem. Eng. Data 61 (2016) 2078-2082, DOI 10.1021/acs.jced.5b01104, Table 2 — isothermal p-x at 412.6/443.2/483.2 K, no measured y (open copy, Cranfield CERES, retrieved 2026-11-04); (3) NIST Chemistry WebBook SRD 69 acetic acid page — Antoine params log10(P/bar)=4.68206-1642.54/(T/K-39.764) valid 290.26-391.01 K from McDonald, Shrader & Stull, JCED 4 (1959) 311, DOI 10.1021/je60004a009, plus TRC T_boil 391.2 ± 0.6 K (retrieved 2026-11-04).
- NOT FOUND / gaps: data/components.yaml has NO AcOH entry (CAS 64-19-7) — cases cannot resolve until AcOH is curated (flagged in pack.yaml header). Marek 1955 (DOI 10.1135/cccc19551490) landing page retrieves but its full data table is not openly retrievable — NOT FOUND (paywalled/archived). Zhang 2011 (FPE 305, DOI 10.1016/j.fluid.2011.03.006) ThermoML record checked and EXCLUDED — its archived datasets are the ternaries with propyl/isobutyl acetate (liquid fractions sum < 1), not the binary. Vercher 2001 ThermoML record (je010106p) 404s on trc.nist.gov. The 1967 paper states "atmospheric pressure" without a barometric reading; P = 101325 Pa is the convention, flagged per point. hoc_dimer row notes (T-19) apply: the package's liquid side is ideal, so binding the binary cases as pass/fail needs a regressed GE pair or widened tolerances — the pack pins the data independently.
- Tests run + result: none (data-only PR; no code touched). Scripted checks on the pack: YAML parses (75 cases), ids unique, z sums to 1, Sebastiani series monotone in T vs x_H2O, isotherm P ranges ordered — all clean.
- Next / open questions: Stomato bot to review PR #339 and decide binding (needs AcOH curation + the GE-pair decision above). Candidate open follow-up: transcribe Marek 1955 from the print/archive if it becomes openly accessible.
- Heartbeats: single-session run (claim 12:10 PM → push 12:12 PM CST); no heartbeat cadence needed.
### T4 — Obvious — 2026-11-04 12:11 PM CST
- Done: API liquid density pack. Found the procedure itself in a public API e-ballot draft, "Technical Data Book: Part 6 – Density" (TDB-6_e1 draft.pdf): Procedure 6A2.3 "Density of Liquid Petroleum Fractions at Low Pressures with the Modified Rackett Equation (1992)" — the procedure historically numbered 6A3.5 — with its complete worked example (MeABP 538 °F, API gravity 30.6 → rho(160 °F) = 0.8353 g/mL; experimental 0.8343 g/mL), printed M/Tpc/Ppc correlations, and ZRA back-calculation from SG. Every printed number was re-derived independently in Python before transcription (agreement ≤0.03 % on intermediates, 0.0002 g/mL on the final density). Corroborating open reproduction: Ramos-Pallares 2017 PhD thesis (Calgary) — Spencer–Danner modified Rackett, ZRA tuned at 15.6 °C to SG, Tables E.1–E.6 pseudocomponent parameters (kept as parameter data, not cases: reconstruction deviates −1 to −2 %). IJERT 2024 paper independently confirms the historical number: "procedures 11A4.1 and 6A3.5 of API (1997)".
- Outputs (paths / branch / commit / PR #): `data/validation/packs/T4/{notes.md,data.csv,pack.yaml}`; branch `obv/T4`, commit fb4eb4d; PR #338 (`obv/T4` → `chem-engine`). No code changes; no V1 files touched.
- Sources used: API TDB-6 e-ballot draft (URL + pages in notes.md §1–§3, retrieved 2026-11-04); Ramos-Pallares 2017 U Calgary thesis (notes.md §4); IJERT V13 IS 070052 (notes.md §5).
- NOT FOUND / gaps: Riazi MNL50 §5.8/Ch.7 body text (public sample PDF is TOC-only; full book paywalled); Rackett 1970 original paper (paywalled); published TDB 1997/2016 editions (paywalled); Nji Calgary thesis link dead (returned HTML). No open reproduction of the *published* 6A3.5 exists — the ballot draft of the renumbered procedure is the closest open artifact. Details in notes.md §6.
- Tests run + result: none — data-only pack, no code touched; cases carry `package: pending:api-liquid-density` (adapter not registered; listed blocked in V1's progress log) so the harness skips them until bound. Pack named pack.yaml per PROTOCOL.md.
- Next / open questions: Stomato bot to bind pack.yaml when the API-liquid-density adapter spec registers its row (reconcile pending id `api-liquid-density` then). Ballot-draft caveat: numbers are as balloted, published TDB remains authority of record (flagged in notes.md §1).
- Heartbeats: 12:10 PM CST — sources located and verified (below).

### T4 — Obvious — 2026-11-04 12:10 PM CST
- 12:10 PM CST — heartbeat: sources located and verified. Primary: public API e-ballot draft "Technical Data Book: Part 6 – Density" (TDB-6_e1 draft.pdf, eballotprodstorage.blob.core.windows.net) containing the modified-Rackett procedure for petroleum fractions at low pressure (1992 procedure, historically numbered 6A3.5; renumbered 6A2.3 in the draft) with a complete worked example. All example numbers reproduced independently in Python (SG, M, Tpc, ppc, ZRA, rho at 160 F) before transcription. Writing pack files to data/validation/packs/T4/ on obv/T4 next.

### Board — Stomato bot — 2026-11-04 12:15 PM
- PROTOCOL.md rewritten as the Obvious playbook. T1 dropped as stale; T1r + T3-T8 dispatched to Obvious (project ids in Shared notes). All data tasks write packs to data/validation/packs/<id>/ (pack.yaml, not cases*.yaml) so they don't collide with V1's files.

### T6 — Obvious — 2026-11-04 12:10 PM
- 12:10 PM CST — Obvious (T6): claimed; three open sources verified with full numeric tables (CABEQ 2015 PS/toluene; Tanbonliong/Prausnitz UC thesis; CABEQ 2014 PMMA/2-butanone). Building pack now.

<!-- Template:
### <id> — <owner> — <YYYY-MM-DD HH:MM>
- Done:
- Outputs (paths / branch / commit):
- Sources used:
- NOT FOUND / gaps:
- Tests run + result:
- Next / open questions:
-->

### V1 — Claude Code (board sync) — 2026-11-04 11:45 AM
- Done: Run resumed 11:35 AM after the 5-hour usage reset. val-infra (8a7d545, 296e6f6) fast-forwarded into chem-engine at 11:35.
- Outputs (paths / branch / commit): chem-engine; progress in `~/stomato-val-progress.md`.
- Tests run + result (from progress log): ruff, format, mypy (656 files), lint-imports (3 kept), full pytest --extra saft exit 0, audit PASS, frontend typecheck/lint/check:api, vitest 147/147.
- Next / open questions: remaining workstreams (units-a/b/c, special, gphi-corr, etc.) continue; blocked models listed in progress log: COSMO-SAC, SR-POLAR, Polymer SRK, API liquid density.

### T2 — Obvious — 2026-11-04 10:57 AM
- Done: Coordination loop test — read `agents/PROTOCOL.md`, added T2 row to the task board, committed and pushed this handoff to `agents-board`.
- Outputs (paths / branch / commit): `agents/BOARD.md` on branch `agents-board`, commit _this commit_.
- Sources used: `agents/PROTOCOL.md`, `agents/BOARD.md` (both on `agents-board`).
- NOT FOUND / gaps: T1 thermo reference-data results are not visible to me — the board shows T1 (Obvious, in progress, branch `obv/T1`, results in the Obvious project, no push access yet), but the actual T1 outputs are not on `agents-board` and were not part of this test's scope. Marking NOT FOUND for T1 result contents.
- Tests run + result: none (board-only edit; no code touched).
- Next / open questions: confirm push access to `agents-board` works end-to-end; T1 owner to push results to `obv/T1` once GitHub App access is granted (see Open questions).

## Shared notes

### Decisions
- 2026-11-04: Heavy units stay at catalogue R2 for now; validation comes first.
- 2026-11-04: Licence questions deferred (non-commercial); still record the source of every value.
- 2026-11-04: Companies will bring their own data; structure must accept user parameter sets with recorded sources.

### Open questions
- Does the Obvious workspace tied to the API key hold the $20k credits?
- Obvious GitHub App install on the Stomato repo (needed for Obvious to push `obv/*` branches).
  - 2026-11-04 11:11 AM (board sync): Obvious pushed commit bea3182 to `agents-board` (T2), so its push access works for this branch; no `obv/*` branch exists on origin yet, so T1 results are still only in the Obvious project.

### Obvious projects (dispatched 2026-11-04 12:20 PM CST, workspace wks_IDdvA1UG)
| task | project | execution |
|---|---|---|
| T1r | prj_4bg1MlBW | exec_8Tb8jWO0 |
| T3 | prj_Rh6o5zhG | exec_lCRgWdzP |
| T4 | prj_mYOI5T12 | exec_Jq1IfIUF |
| T5 | prj_UL5jKG4T | exec_ctQh3Dda |
| T6 | prj_MiBfJLDC | exec_5ZBp3PUC |
| T7 | prj_J0x7iuFO | exec_mbxJeQ2t |
| T8 | prj_1JiMmh1a | exec_1DS7Neqa |

### Sources found
| model / unit | dataset | citation | DOI / URL | added by |
|---|---|---|---|---|
