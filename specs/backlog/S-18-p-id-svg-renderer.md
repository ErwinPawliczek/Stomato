# S-18: P&ID SVG renderer

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `diagram`, name `pid`

## Goal
Render a PID to a clean, readable SVG with standard symbols.

## Files (create only these)
- `src/ngdesign/render/pid_svg.py`
- `src/ngdesign/render/symbols.py`
- `tests/render/test_pid_svg.py`

## Method
Layout: equipment left to right in topological order of lines (graph from LineEnd links),
lines as orthogonal polylines between nozzle anchor points; inline items drawn in order along the line.
Symbols (ISA 5.1 / ISO 10628 style, simple geometric): vessel (rounded rect), pump (circle + triangle),
compressor (trapezoid), exchanger (circle with zigzag), gate/ball/globe/check/control/PSV valve symbols,
instrument bubble (circle with tag text, function on top, loop below), reducers, drains/vents.
Text: every equipment tag, line number (along the line), valve tag, instrument tag.
No external dependencies; build SVG with xml.etree. Deterministic output.
`symbols.py` holds symbol functions so the PFD renderer can reuse them.

## Acceptance criteria
- [ ] Render of `sample_pid()` (and of that PID after applying every registered pid_rule) is well-formed XML with root `svg`
- [ ] Every equipment tag, line number, valve tag and instrument tag appears as text in the SVG
- [ ] No two equipment bounding boxes overlap (test parses the generated rects)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Interactive viewer; DXF.
