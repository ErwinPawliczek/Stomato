# F-02: L2 Results panel

- **Depends on:** F-01; backend B-02 for live data (use mocks until then)
- **Rules:** frontend/AGENTS.md

## Goal
Results tab: Solve button, stream table (T, P, flows, vapor fraction), unit duty/power table.

## Files
- `frontend/src/views/ResultsView.tsx`
- `frontend/src/views/ResultsView.test.tsx`
- `frontend/mocks/solved.json`

## Acceptance criteria
- [ ] Solve calls api.solve() (add to client.ts; mock returns mocks/solved.json)
- [ ] 501 from backend shows 'Solver not available yet' instead of crashing
- [ ] Table sorted by stream id; units per src/units.ts
- [ ] Test: renders one row per stream in mocks/solved.json
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
