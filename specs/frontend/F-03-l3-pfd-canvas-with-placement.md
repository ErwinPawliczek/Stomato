# F-03: L3 PFD canvas with placement

- **Depends on:** B-03 for real SVG (mock SVG until then)
- **Rules:** frontend/AGENTS.md

## Goal
Show the PFD SVG; drag elements with data-tag to move them; positions persist via api.place('pfd', ...).

## Files
- `frontend/src/views/SvgCanvas.tsx (shared pan/zoom/drag over an SVG string)`
- `frontend/src/views/PfdView.tsx`
- `frontend/src/views/PfdView.test.tsx`
- `frontend/mocks/pfd.svg`

## Acceptance criteria
- [ ] Pan (drag background) and zoom (wheel) work
- [ ] Dragging a [data-tag] group calls api.place on drag end with SVG coordinates
- [ ] After placement the view re-fetches the SVG
- [ ] Clicking an element shows its tag in a side panel
- [ ] Test: simulated drag on V-101 calls place('pfd','V-101',...)
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
