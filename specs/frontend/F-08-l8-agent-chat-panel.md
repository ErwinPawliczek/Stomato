# F-08: L8 Agent chat panel

- **Depends on:** B-08
- **Rules:** frontend/AGENTS.md

## Goal
Chat panel that sends messages to POST /api/agent and shows tool calls and resulting project changes.

## Files
- `frontend/src/views/AgentView.tsx`
- `frontend/src/views/AgentView.test.tsx`

## Acceptance criteria
- [ ] Streams assistant text; each tool call shown as a collapsible row
- [ ] After a project-changing tool call the other tabs refresh
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
