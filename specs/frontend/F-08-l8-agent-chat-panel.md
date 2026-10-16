# F-08: L8 Agent chat panel

- **Depends on:** B-08
- **Rules:** frontend/AGENTS.md

## Goal
Chat panel that sends messages to POST /api/agent and shows tool calls and resulting project changes.

## Files
These files already exist from PR #69 with the chat layout with a sample conversation and a disabled Send, in the F-09 theme. Extend them; keep the layout.
- `frontend/src/views/AgentView.tsx`
- `frontend/src/views/AgentView.test.tsx`

## Acceptance criteria
- [ ] Streams assistant text; each tool call shown as a collapsible row
- [ ] After a project-changing tool call the other tabs refresh
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
