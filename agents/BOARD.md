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
| T4 | API liquid density: public reproductions of API TDB 6A3.5 / Rackett-type petroleum correlations with worked examples | Obvious | claimed | obv/T4 | 2026-11-04 12:08 PM |
| T5 | COSMO-SAC: open sigma-profile DBs (VT-2005, UD/NIST Bell 2020) + independent gamma-inf/VLE pack | Obvious | claimed | obv/T5 | 2026-11-04 12:07 PM |
| T6 | Polymer SRK / polymer-solvent: open polymer-solvent VLE data independent of Kiss 2009 | Obvious | claimed | obv/T6 | 2026-11-04 12:06 PM |
| T7 | Acetic acid/water open VLE pack (hoc_dimer L2 gap) | Obvious | claimed | obv/T7 | 2026-11-04 12:12 PM |
| T8 | Bring reformer_cat.yaml (PR #329) + control_valve.yaml (PR #282) case files into a chem-engine PR | Obvious | claimed | obv/T8 | 2026-11-04 1:20 PM |
| T2 | Board loop test | Obvious | done | agents-board | 2026-11-04 10:57 AM |

Status values: `open`, `claimed`, `in progress`, `blocked`, `review`, `done`, `dropped`.

## Handoffs

### Board — Stomato bot — 2026-11-04 12:15 PM
- PROTOCOL.md rewritten as the Obvious playbook. T1 dropped as stale; T1r + T3-T8 dispatched to Obvious (project ids in Shared notes). All data tasks write packs to data/validation/packs/<id>/ (pack.yaml, not cases*.yaml) so they don't collide with V1's files.

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
