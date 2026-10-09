# S-02: B31.3 pipe wall thickness and schedule selection

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `wall_thickness_b313`

## Goal
Implement the `wall_thickness_b313` correlation as a callable plugin. Golden cases already exist in `data/golden/wall_thickness_b313.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/wall_thickness.py`
- `tests/sizing/test_wall_thickness.py`

## Method
ASME B31.3 304.1.2: `t = P*D/(2*(S*E*W + P*Y))`, P and S in MPa, D = pipe OD from `ngdesign.data.pipe(nps, sched)`. Nominal = (t + CA)/(1 - mill_tol). Select the thinnest schedule in order [10,20,30,40,STD,60,XS,80,100,120,140,160,XXS] available for that NPS with wall >= nominal (ties go to the earlier entry). Raise ValueError if none suffices.

Also provide `select_schedule(nps_in, design_pressure_gauge_Pa, pipe_class: str)` that reads S, E, W, Y and CA from `ngdesign.data.pipe_classes()`.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def wall_thickness_b313(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k wall_thickness_b313` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
