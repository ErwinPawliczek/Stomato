# S-30: Sequential-modular flowsheet solver

- **Wave:** 1
- **Depends on:** S-01
- **Plugin:** kind `solver`, name `sequential_modular`

## Goal
Solve a Flowsheet: flash feeds, run units in dependency order, converge recycles.

## Files (create only these)
- `src/ngdesign/solver/sequential_modular.py`
- `tests/solver/test_sequential_modular.py`

## Method
Flash feed streams with flash_pt. Build the unit graph; topological order; if cycles exist,
choose tear streams (minimum set, simple heuristic) and converge with Wegstein acceleration (bounded q in
[-5, 0]) on component flows, T and P; tolerance 1e-6 relative, max 100 iterations. Units come from
`registry.create("unit", spec.kind)`. Returns SolvedFlowsheet (converged, iterations, all stream states,
unit results). Tests must not depend on specific unit plugins: register small fake units inside the test
module (pure Python, using the thermo fixture) including one recycle loop.

## Acceptance criteria
- [ ] Own tests: linear chain, a split-and-remix, and a recycle loop converge; non-converging case returns converged=False rather than raising
- [ ] Once S-24..S-29 are merged, solving `flowsheets.slice.build()` converges (separate test, skips if any slice unit kind is not registered)
- [ ] ruff, mypy and full `uv run pytest -rs` green
- [ ] No locked file touched; only the files listed above created

## Out of scope
Equation-oriented solving, spec/adjust blocks.
