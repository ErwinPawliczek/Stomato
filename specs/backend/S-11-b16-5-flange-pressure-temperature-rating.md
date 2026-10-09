# S-11: B16.5 flange pressure-temperature rating

- **Wave:** 0
- **Depends on:** none
- **Plugin:** kind `correlation`, name `flange_rating_b165`

## Goal
Implement the `flange_rating_b165` correlation as a callable plugin. Golden cases already exist in `data/golden/flange_rating_b165.yaml`.

## Files (create only these)
- `src/ngdesign/sizing/flange_rating.py`
- `tests/sizing/test_flange_rating.py`

## Method
Look up `ngdesign.data.flange_ratings()` for (material_group, class); linear interpolation in temp_F; at or below 100 F use the 100 F value; above table range raise ValueError.

Also provide `min_flange_class(material_group, design_pressure_psig, temp_F) -> int` choosing the lowest class whose rating >= pressure.

Call signature: `__call__(self, **inputs)` taking exactly the `inputs` keys of the golden file, returning a dict with every `expected` key. Also expose a plain typed function for reuse by other modules (e.g. `def flange_rating_b165(...) -> ...`).

## Acceptance criteria
- [ ] `tests/golden/test_correlations.py -k flange_rating_b165` PASSES for every case (none skipped)
- [ ] Own tests: invalid input raises ValueError (negative/zero where physical), plus one hand-checked case
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Anything beyond this correlation.
