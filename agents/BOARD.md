# Stomato agent board

Shared coordination file for all agents working on Stomato. Read `agents/PROTOCOL.md` first.
Times are America/Chicago (CST). Newest handoff on top.

## Task board

| id | title | owner | status | branch | updated |
|----|-------|-------|--------|--------|---------|
| V1 | Validation run: cite reference cases for provisional thermo models, then R2 units | Claude Code | in progress (paused for usage reset, resumes ~11:35 AM) | chem-engine (local run, log `~/stomato-val.log`) | 2026-11-04 10:50 AM |
| T1 | Obvious trial: cited reference data for PR ethane/propane VLE, NRTL ethanol/water VLE, IAPWS-IF97 verification tables | Obvious | in progress | obv/T1 (results currently in Obvious project; no push access yet) | 2026-11-04 10:50 AM |
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

### Sources found
| model / unit | dataset | citation | DOI / URL | added by |
|---|---|---|---|---|
