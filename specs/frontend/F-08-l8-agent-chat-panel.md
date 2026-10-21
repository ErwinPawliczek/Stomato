# F-08: L8 Agent chat panel

- **Depends on:** B-08 (its SSE event schema is fixed below; build against it in `VITE_MOCK` mode first)
- **Rules:** frontend/AGENTS.md

## Goal
A chat panel that sends a message to `POST /api/agent`, streams the assistant's text, shows every tool
call as a collapsible row with its result, and refreshes the other tabs when the project changed.

## Event schema (from B-08; one SSE `data:` line per JSON event)
```
{"type":"text_delta","text":"..."}
{"type":"tool_call","id":"toolu_x","name":"add_unit","input":{...}}
{"type":"tool_result","id":"toolu_x","ok":true,"summary":"V-102 added (scrubber)","result":{...}}
{"type":"project_changed"}
{"type":"done","conversation_id":"c_1","stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1,"cache_read_input_tokens":0}}
{"type":"error","message":"..."}
```
Request: `POST /api/agent` body `{"message": string, "conversation_id"?: string}`; response
`text/event-stream`. `GET /api/agent/{id}` returns the transcript; `DELETE /api/agent/{id}` resets.

## Files
These files exist from PR #69 (chat layout with a sample conversation and a disabled Send, in the F-09
theme). Extend them; keep the layout.
- `frontend/src/views/AgentView.tsx`, `frontend/src/views/AgentView.test.tsx`
- `frontend/src/api/client.ts` — `agent.send(message, conversationId, onEvent)` using `fetch` + a
  `ReadableStream` reader (SSE parsing lives here, nowhere else); mock branch streams the canned event
  sequence in `frontend/mocks/agent-events.json` (new) with a short delay per event.
- `frontend/mocks/agent-events.json` — the showcase conversation (sour gas → MDEA → TEG → compressor)
  as the event list above.

## Acceptance criteria
- [ ] Streams assistant text as it arrives; each tool call is a collapsible row showing name, input and
      result summary (full result on expand); errors render inline, never as a blank
- [ ] After a `project_changed` event the Flowsheet/Results/PFD/P&ID tabs re-fetch (one shared signal)
- [ ] Send is enabled with text, disabled while streaming; Enter sends, Shift+Enter newlines; the
      conversation id persists across sends in the session
- [ ] `VITE_MOCK=1` demo works without a backend
- [ ] typecheck, lint, test (render + a streamed mock session), build green
- [ ] Only files under `frontend/` changed
