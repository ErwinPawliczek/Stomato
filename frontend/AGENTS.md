# frontend/AGENTS.md

React 18 + TypeScript + Vite. You work ONLY inside `frontend/`. The backend is someone else's.

## Commands (run inside frontend/)
```
npm ci
VITE_MOCK=1 npm run dev   # UI against mocks, no backend needed
npm run dev               # UI against backend on :8000 (uv run uvicorn ngdesign.api.app:app --port 8000)
npm run typecheck && npm run lint && npm test && npm run build   # what CI runs
```

## Rules
- All backend access goes through `src/api/client.ts`. Never `fetch` anywhere else.
- Types come from `src/api/schema.d.ts`, generated from `../openapi.json`. Never edit it by hand.
  If you need an endpoint or field that does not exist: stop, and write in the PR what you need.
  Until it exists, add sample data to `mocks/` and a mock branch in `client.ts`.
- One view per file in `src/views/`; register it in the `TABS` list in `src/App.tsx`.
- Diagrams arrive from the backend as SVG with `data-tag="V-101"` attributes on elements. Use those
  attributes for selection and dragging; never parse drawing geometry yourself.
- Placement: on drag end call `api.place(view, tag, {x, y})`. The backend stores it; re-render from
  the response. Never keep layout only in component state.
- Units shown to users: degC, kPa(g), kmol/h, kg/h, kW. Convert in one helper (`src/units.ts`).
- Accessible: buttons are buttons, tabs use role="tab", every interactive element reachable by keyboard.
- No new dependencies without saying so in the PR (package.json is locked).

## Definition of done
1. typecheck, lint, test, build all green.
2. A test in `src/**/*.test.tsx` covering the change (render + interaction with @testing-library/react).
3. PR title `FE: ...` or `Fix: ...`; description says how to check it in the browser.

## Never
- Touch files outside `frontend/` (CI rejects mixed PRs).
- Weaken or skip a test.
