# S-42: Absorber stage-stepping diagram

- **Wave:** stretch
- **Depends on:** S-05
- **Plugin:** kind `diagram`, name `absorber_stages`

## Goal
McCabe-Thiele style staircase for the TEG contactor.

## Files (create only these)
- `src/ngdesign/render/absorber_stages.py`
- `tests/render/test_absorber_stages.py`

## Method
Equilibrium line y = m x, operating line from (x_top, y_out) with slope L/G; step stages from the top; render SVG with stage count.

## Acceptance criteria
- [ ] Stepped stage count equals Kremser (S-05) within 0.01 for linear equilibrium
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Nonlinear VLE.
