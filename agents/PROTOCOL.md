# Agent coordination protocol

Agents: **Stomato bot** (coordinator, sole merger), **Claude Code** (local coding runs), **Obvious** (research, data extraction, scripted PRs).
The board is `agents/BOARD.md` on branch `agents-board`. It is the only channel between agents.

## Claiming work
1. Pick an `open` row whose owner is you (or unassigned, if the Stomato bot allows it).
2. Set status to `claimed`, put your branch name, update the `updated` timestamp, commit to `agents-board`.
3. Only one owner per task. If you need help, add an `open` sub-task (`<id>.1`, `<id>.2`) instead of editing someone else's row.
4. When blocked, set `blocked` and write the reason in Open questions.

## Branches
- Obvious: `obv/<id>` · Claude Code: `claude/<id>` · Stomato bot: `bot/<id>`.
- Branch from `chem-engine`. Never commit to `main` or `chem-engine` directly.

## Handoff (required at end of every task)
Add an entry at the top of **Handoffs** in BOARD.md with: done summary, output paths/branch/commit,
sources used, NOT FOUND gaps, tests run and result, next steps/questions. Set status to `review`.

## Rules
- **Cite every value**: source citation, DOI or URL, table/figure, page.
- **Never invent or estimate data.** If not found, write `NOT FOUND` — do not fill gaps or loosen tolerances to pass.
- **Never touch `main` or locked files** (`pyproject.toml`, `uv.lock`, import-rule config, locked validation data, CLAUDE.md/AGENTS.md) without Erwin's sign-off recorded under Decisions.
- **Nothing merges until the full test suite passes** (Python + frontend) on the merge candidate.
- **Only the Stomato bot merges into `chem-engine`.**
- **No personal data, secrets, or API keys** in the repo, board, or prompts to external agents.
- Keep entries short; link to files instead of pasting large output.
