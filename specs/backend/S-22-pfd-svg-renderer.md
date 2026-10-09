# S-22: PFD SVG renderer

- **Wave:** 0
- **Depends on:** none (reuses S-18 symbols if merged, else draws its own)
- **Plugin:** kind `diagram`, name `pfd`

## Goal
Render a SolvedFlowsheet as a PFD with a stream table.

## Files (create only these)
- `src/ngdesign/render/pfd_svg.py`
- `tests/render/test_pfd_svg.py`

## Method
Major equipment only, left to right by topological order of the Flowsheet; main streams as
orthogonal lines with arrows and stream-number diamonds; feeds enter from the left, products leave right.
Stream table below: per stream T (C), P (kPa g), molar flow (kmol/h), mass flow (kg/h, if phases present),
vapor fraction. Equipment summary row: duty (kW) / power (kW) from UnitResult.
Test fixture: build a SolvedFlowsheet for `flowsheets.slice.build()` with hand-made StreamStates (no thermo
needed: construct StreamState directly with plausible numbers).

## Acceptance criteria
- [ ] Well-formed SVG; every unit tag and stream id appears as text; the table has one row per stream
- [ ] Deterministic: rendering twice gives identical strings
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Valves and instruments (that is the P&ID).
