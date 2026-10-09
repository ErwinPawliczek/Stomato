# S-41: Phase envelope plot

- **Wave:** stretch
- **Depends on:** S-01
- **Plugin:** kind `diagram`, name `phase_envelope`

## Goal
P-T phase envelope with operating points.

## Files (create only these)
- `src/ngdesign/render/phase_envelope.py`
- `tests/render/test_phase_envelope.py`

## Method
Trace bubble and dew curves (thermo flashes at VF=0 and VF=1 across T); mark cricondenbar, cricondentherm and each stream's (T, P). SVG output.

## Acceptance criteria
- [ ] Well-formed SVG; cricondentherm above every dew point traced
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Hydrate curve.
