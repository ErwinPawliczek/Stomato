# S-35: Slice end to end + CLI

- **Wave:** 3
- **Depends on:** all slice specs
- **Plugin:** none (wiring)

## Goal
Make the demo test pass and write every drawing to disk.

## Files (create only these)
- `src/ngdesign/cli.py`
- `tests/e2e/test_cli.py`
- `tests/e2e/test_slice.py (remove the xfail marker only)`

## Method
`python -m ngdesign.cli slice --out out/` runs: thermo pr -> solver -> sizers -> pid_builder ->
all pid_rules applied repeatedly until nothing changes (max 5 passes; rules can create work for each
other, e.g. a new PSV line needs isolation) -> pfd + pid SVG -> router -> iso SVG per line (+ DXF if registered) -> index.html linking
everything with the stream table. Remove the xfail marker from tests/e2e/test_slice.py.

## Acceptance criteria
- [ ] `tests/e2e/test_slice.py` PASSES with xfail removed
- [ ] CLI writes pfd.svg, pid.svg, iso_*.svg, index.html
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Web server.
