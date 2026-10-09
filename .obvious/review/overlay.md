## Tooling-Handled (skip these)
- Formatting, imports, lint: ruff (backend), eslint (frontend)
- Types: mypy (backend), tsc strict (frontend)
- Locked-path and frontend/backend-mixing checks: CI guard job

## High-Scrutiny Paths
- src/ngdesign/units/**, src/ngdesign/sizing/**, src/ngdesign/thermo/**: check equations against the cited source,
  SI units, and that results come from oracle-tested code, not hard-coded numbers
- Any test change: block if a test was removed, skipped, xfailed, or a tolerance loosened
- frontend/src/api/client.ts: all backend access must go through it

## References
- AGENTS.md, frontend/AGENTS.md, specs/INDEX.md
