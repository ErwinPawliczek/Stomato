# F-05: L5 Plot plan (top view) placement

- **Depends on:** F-03; B-05
- **Rules:** frontend/AGENTS.md

## Goal
2D top-view plot plan: drag equipment footprints in mm; save via PUT /api/project/layout/plot/{tag}; button 'Re-route'.

## Files
- `frontend/src/views/PlotView.tsx`
- `frontend/src/views/PlotView.test.tsx`

## Acceptance criteria
- [ ] Grid snap 500 mm
- [ ] Elevation input per selected equipment (z)
- [ ] Re-route triggers backend route and refreshes
- [ ] typecheck, lint, test, build green
- [ ] Only files under frontend/ changed
