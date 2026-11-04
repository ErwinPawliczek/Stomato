# Stomato agent board

Shared coordination file for all agents working on Stomato. Read `agents/PROTOCOL.md` first.
Times are America/Chicago (CST). Newest handoff on top.

## Task board

| id | title | owner | status | branch | updated |
|----|-------|-------|--------|--------|---------|
| V1 | Validation run: cite reference cases for provisional thermo models, then R2 units | Claude Code | in progress (resumed 11:35 AM after usage reset; val-infra merged into chem-engine 11:35) | chem-engine (local run, log `~/stomato-val.log`) | 2026-11-04 11:45 AM |
| T1 | Obvious trial: cited reference data for PR ethane/propane VLE, NRTL ethanol/water VLE, IAPWS-IF97 verification tables | Obvious | in progress | obv/T1 (results currently in Obvious project; no obv/* branch on origin yet) — STALE >45 min (no update since 10:50 AM) | 2026-11-04 11:45 AM |
| T2 | Board loop test | Obvious | done | agents-board | 2026-11-04 10:57 AM |

Status values: `open`, `claimed`, `in progress`, `blocked`, `review`, `done`, `dropped`.

## Handoffs

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

### Sources found
| model / unit | dataset | citation | DOI / URL | added by |
|---|---|---|---|---|
