---
description: Reproduce and fix a UI bug with a regression test
argument-hint: <what's wrong, steps, expected vs actual>
---
Bug: $ARGUMENTS

1. Read frontend/AGENTS.md. Edit files under frontend/ only.
2. If the cause is in the backend (wrong numbers, 4xx/5xx other than 501), do not edit backend code:
   run `gh issue create --label bug,backend` with steps, expected vs actual, then stop.
3. Write a failing test in frontend/src/**/*.test.tsx that reproduces the bug.
4. Make the smallest fix. In frontend/ run: npm run typecheck && npm run lint && npm test && npm run build
5. Tell me exactly what to click in the browser to confirm the fix.
