# Agent protocol — standing playbook

Agents: **Stomato bot** (coordinator, sole merger), **Claude Code** (local coding runs on Erwin's PC), **Obvious** (research, data extraction, scripted PRs).
The board is `agents/BOARD.md` on branch `agents-board` of `ErwinPawliczek/Stomato`. It is the only channel between agents.
All times on the board are **America/Chicago (CST, UTC-6)**. Convert your clock (UTC) before writing: 18:00 UTC = 12:00 PM CST.

## How the Stomato bot works
- It writes tasks on the board, starts Obvious jobs, and runs Claude Code on Erwin's PC.
- Every 15 minutes it reads the board and every `obv/*` / `claude/*` branch, updates status from what is actually pushed, and replies under Handoffs.
- It cannot see inside an Obvious project. **If it isn't pushed, it didn't happen.** A task silent for 45 minutes is treated as stale and may be re-dispatched as `<id>r`.
- It runs the full test suite on Erwin's PC and is the only agent that merges into `chem-engine`.

## Obvious playbook (do these in order)
1. **Read first:** `agents/PROTOCOL.md` and `agents/BOARD.md` on `agents-board`, then `AGENTS.md` on `chem-engine`.
2. **Claim before starting:** edit your task row: status `claimed`, branch `obv/<id>`, `updated` = now in CST. Commit + push to `agents-board` (`git pull --rebase` first; only touch your own row and your own Handoffs entry).
3. **One task = one branch:** create `obv/<id>` from `origin/chem-engine`. Never commit to `main`, `chem-engine`, or anyone else's branch.
4. **Heartbeat every ~20 min:** append one line `- HH:MM CST — <progress>` under your task's Handoffs entry and push to `agents-board`. Also push work-in-progress commits to `obv/<id>`.
5. **Finish:** push outputs to `obv/<id>`; open a PR `obv/<id>` → `chem-engine` (**never `main`**); fill the handoff template below; set status `review`; push `agents-board`.
6. **Fail / blocked:** still push whatever you have to `obv/<id>`, write a `BLOCKED:` handoff saying exactly what stopped you (URL, error, missing access), set status `blocked`, push `agents-board`. Never end silently.
7. **Stay small:** do only the task's scope. If you find more work, add an `open` sub-task row `<id>.1` instead of doing it.

## Handoff template (top of Handoffs, newest first)
```
### <id> — Obvious — <YYYY-MM-DD HH:MM CST>
- Done:
- Outputs (paths / branch / commit / PR #):
- Sources used:
- NOT FOUND / gaps:
- Tests run + result:
- Next / open questions:
- Heartbeats:
```

## Data rules
- **Cite every value:** author/year, DOI or URL, table or figure, page, retrieval date — on every row or case.
- Only values read from a document you actually retrieved. **Never invent, estimate, interpolate, tune, or recall from memory.**
- Missing → write `NOT FOUND` with where you looked. Paywalled → `NOT FOUND (paywalled: <URL>)`.
- Prefer open sources: NIST ThermoML / WebBook, IUPAC-NIST SDS, JCED/FPE open data, theses, government reports, textbooks' worked examples.
- **Data packs** go in `data/validation/packs/<id>/` as `data.csv` (one row per point, with source columns) + `pack.yaml` (cases in the same schema as `data/validation/<family>/cases.yaml`: `id`, `package`, `components`, `z`, `T`, `P`, `source`, `expected`). Name it `pack.yaml`, **not** `cases*.yaml`, so the harness does not run it until the Stomato bot binds it. Units: K, Pa, mole fractions, J/mol.

## Code rules
- Follow `AGENTS.md`. Do not edit locked files: `pyproject.toml`, `uv.lock`, `.importlinter`, `CLAUDE.md`, `AGENTS.md`, `tests/golden`, `tests/property`, `data/golden`, `.github`. Edits under `data/validation/` and `data/validation_units/` **are allowed**.
- Run the repo's tests in your sandbox if you can (`uv run --all-groups pytest -rs`, or the relevant subset) and report the exact command and result. If you can't run them, say so.
- Only the Stomato bot merges into `chem-engine`, after the full suite passes on Erwin's PC.
- No secrets, API keys, or personal data in the repo, board, or PRs.
