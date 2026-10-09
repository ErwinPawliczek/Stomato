# Dispatching agents

Three ways, pick whichever the workspace supports:
1. **GitHub issue with @claude** (built in): use the "UI change" or "Bug" issue template. Keeping the
   `@claude` line dispatches an agent that opens a PR. Needs the Claude GitHub App + ANTHROPIC_API_KEY secret.
2. **Obvious workspace agents:** paste `agents/implementer.md` with the spec path filled in.
3. **Local Claude Code:** `claude "$(cat agents/implementer.md)"` after filling in the task.

Roles: implementer (builds a spec), reviewer (checks a PR), fixer (failing CI or bug).
Backend specs: `specs/backend/`. Frontend specs: `specs/frontend/`. Order: `specs/INDEX.md`.
