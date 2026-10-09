# F-06: L6 Isometric viewer

- **Depends on:** B-06
- **Rules:** frontend/AGENTS.md

## Goal
List of lines; selecting one shows its isometric SVG, BOM table and cut list.

## Files
- `frontend/src/views/IsoView.tsx`
- `frontend/src/views/IsoView.test.tsx`
- `frontend/mocks/iso_6in.json`

## Acceptance criteria
- [ ] Line list from API; BOM and cut list as tables; Download SVG button
- [ ] Test: selecting a line renders its BOM
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
