# F-04: L4 P&ID canvas

- **Depends on:** F-03 (reuses SvgCanvas); B-04
- **Rules:** frontend/AGENTS.md

## Goal
Same canvas for P&ID; side panel lists valves and instruments for the selected equipment/line.

## Files
- `frontend/src/views/PidView.tsx`
- `frontend/src/views/PidView.test.tsx`
- `frontend/mocks/pid.svg`

## Acceptance criteria
- [ ] Drag/persist via api.place('pid', ...)
- [ ] Search box highlights a tag or line number
- [ ] Test: search 'PSV' highlights matching elements
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
