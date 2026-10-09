# S-19: Isometric SVG renderer

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `iso_renderer`, name `svg`

## Goal
Render one RoutedLine as a fabrication isometric with dimensions, welds, BOM and cut list.

## Files (create only these)
- `src/ngdesign/render/isometric_svg.py`
- `tests/render/test_isometric_svg.py`

## Method
Projection: x' = (x - y)*cos30, y' = -(z + (x + y)*sin30) (screen y down). Draw centerline
single-line style: pipe as lines, elbows as arcs or bend markers, flanges as double ticks, valves as bowtie,
weld dots at every butt/socket-weld joint (consecutive components except flange-to-flange). Dimension each
straight run with its centre-to-centre length in mm along the projected axis. Flow arrow on the first pipe.
North arrow. Title block (TitleBlock) from the PidLine matching line_number in the PID (test pressure =
1.5 x design gauge pressure, hydrotest). BOM: group identical descriptions; pipe quantity in metres.
Cut list: one CutPiece per PIPE component, length = component length (mm), spool "SP-1" for all until spool
breaks exist. total_pipe_length_mm = sum of PIPE lengths.
If the PID has no matching line, use defaults from the RoutedLine (class from components).

## Acceptance criteria
- [ ] `tests/property/test_isometric.py` PASSES (well-formed SVG, lengths, BOM elbows, weld count, title)
- [ ] Own test: every pipe run's dimension text appears in the SVG
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
DXF (S-23), spool splitting, supports.
