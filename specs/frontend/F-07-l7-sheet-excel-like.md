# F-07: L7 Sheet (Excel-like)

- **Depends on:** B-07
- **Rules:** frontend/AGENTS.md

## Goal
Grid of cells; a cell holds a number, a variable address (=S-003.T) or a formula (=K-101.power/1000). Values from POST /api/sheet/eval.

## Files
These files already exist from PR #69 with the plain grid (keyboard navigation, in-memory cells), in the F-09 theme. Extend them; keep the layout.
- `frontend/src/views/SheetView.tsx`
- `frontend/src/views/SheetView.test.tsx`

## Acceptance criteria
- [ ] Keyboard navigation (arrows, Enter to edit)
- [ ] Errors shown per cell
- [ ] Case-study panel: pick a param, range, outputs -> table
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
