# F-01: L1 Flowsheet editor

- **Depends on:** none
- **Rules:** frontend/AGENTS.md

## Goal
Edit unit params and stream feed conditions in the Flowsheet tab; Save calls PUT /api/project.

## Files
- `frontend/src/views/FlowsheetView.tsx (extend)`
- `frontend/src/views/FlowsheetView.test.tsx`
- `frontend/src/units.ts`
- `frontend/src/units.test.ts`

## Acceptance criteria
- [ ] Params editable per unit (number inputs); feed T shown in degC, P in kPa(g), flow in kmol/h (convert via src/units.ts)
- [ ] Save button sends the whole Project via api.putProject (add to client.ts with a mock branch)
- [ ] Invalid input (non-number) disables Save and shows the field in error
- [ ] Test: edit K-101 P_out, save, reload from mock, value persists
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
