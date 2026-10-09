# S-21: Orthogonal pipe router

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `router`, name `orthogonal`

## Goal
Turn P&ID lines into 3D routed lines between equipment nozzles via a pipe rack.

## Files (create only these)
- `src/ngdesign/piping/router_orthogonal.py`
- `src/ngdesign/piping/fittings.py`
- `tests/piping/test_router_orthogonal.py`

## Method
Layout: `layout` maps equipment tag -> origin Vec3 (mm); missing tags are placed along x at
12 000 mm spacing, y = 0, z = 0. Boundary ends are placed 3 000 mm beyond the last/first equipment.
Route each line: start nozzle -> leg along the nozzle facing direction (min 500 mm) -> rise/drop to the rack
elevation (PipingNetwork.rack_elevation_mm) -> run along x -> run along y if needed -> drop to the end nozzle
leg -> end nozzle. Collapse zero-length legs. Every direction change is an ELBOW_90_LR with
centre-to-end = 1.5 * NPS * 25.4 mm (`fittings.py` holds this and later fitting dims). Weld-neck flange
component at each equipment nozzle end (length placeholder 100 mm until H-01 dimensions land).
Pipe schedule from `wall_thickness_b313.select_schedule` if available (import lazily), else "40".
Output must satisfy RoutedLine continuity validation.

## Acceptance criteria
- [ ] Routing `sample_pid()` produces one RoutedLine per PidLine, each passing contract validation
- [ ] Every elbow joins two orthogonal legs; no pipe segment passes through an equipment envelope (envelope = 2 m cube around each origin unless provided)
- [ ] `tests/property/test_isometric.py`-style invariants hold when the routed lines are fed to any registered iso_renderer (test skips if none)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Optimal routing, clash avoidance between lines, slopes.
