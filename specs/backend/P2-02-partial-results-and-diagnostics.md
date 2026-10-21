# P2-02: Partial results, per-unit error records and convergence history

- **Phase:** 2
- **Depends on:** P1-02 (per-flowsheet slate), P1-03
- **Packages you may edit:** `ngdesign.contracts` (`flowsheet.py`: `SolvedFlowsheet`, new `diagnostics.py`), `ngdesign.solver`, `ngdesign.api` (only `routes_solve.py` and the project-scoped solve route in `routes_projects.py`, status handling only) and `ngdesign.agent/engine.py` (only `solve_project`, the shared solve helper, to return partial results with HTTP 200), `tests/contracts/`, `tests/solver/`, `tests/api/`, `openapi.json` + `frontend/src/api/schema.d.ts` (regenerated)
- **Contract change:** yes — `SolvedFlowsheet` gains `errors`, `history`, `status`
- **Benchmark delta expected:** none (flash counts identical; history recording adds no flashes)

## Goal
A unit that raises aborts the whole solve with a traceback and the UI gets a 500. The engineer needs
the partial result: which units solved, which failed and why, and how the tears converged. This is the
diagnostics panel's data (Phase 4) and the agent's error channel (B-08).

## Files
- Create `src/ngdesign/contracts/diagnostics.py`
  - `UnitError(Model)`: `tag`, `kind`, `error_type` (exception class name), `message`, `stage: Literal
    ["ports","solve","outlet_missing"]`, `upstream: bool` (True when the unit was skipped because an
    inlet came from a failed unit).
  - `TearRecord(Model)`: `iteration`, `stream_id`, `residual_max` (max relative change over the tear
    vector), `residual_vector: dict[str, float]` (per component / T / P), `acceleration: Literal
    ["direct","wegstein","broyden"]`, `q` (Wegstein factor, `None` otherwise).
  - `BlockRecord(Model)`: `units: list[str]`, `tears: list[str]`, `iterations`, `converged`,
    `records: list[TearRecord]`, `wall_s`.
  - `SolveStatus = Literal["converged","not_converged","failed"]`.
- Edit `src/ngdesign/contracts/flowsheet.py` — `SolvedFlowsheet` gains `status: SolveStatus`
  (derived: `failed` if any non-upstream `UnitError`, else `converged`/`not_converged` from `converged`),
  `errors: list[UnitError] = []`, `history: list[BlockRecord] = []`. `converged` and `iterations` keep
  their meaning. Existing fields untouched.
- Edit `src/ngdesign/solver/sequential_modular.py`
  - `_run_units`: a unit exception is caught, recorded as `UnitError(stage="solve")`, its outlet streams
    are left unset, and every downstream unit in the same block whose inlet is missing is recorded as
    `upstream=True` and skipped (no exception). Port-check failures become `stage="ports"` errors
    before any unit runs. A missing outlet state (unit returned no state for a port) is
    `stage="outlet_missing"`.
  - A block with a failed unit stops iterating (one pass) and is marked `converged=False`.
  - Every tear iteration appends a `TearRecord`; every block appends a `BlockRecord` with wall time.
  - Nothing else about the numerics changes: identical converged results, identical flash counts.
- Edit the solve route / shared helper: a solve with `status="failed"` returns HTTP 200 with the
  partial `SolvedFlowsheet` (the UI decides what to show); only invalid projects (validation errors)
  stay 4xx.
- Tests
  - `tests/solver/test_partial_results.py`: a 3-unit chain whose middle unit raises (register a test-only
    unit kind inside the test via `registry.register`) yields `status="failed"`, one `UnitError` for the
    raiser with its message, one `upstream=True` for the third unit, the first unit's result present.
  - `tests/solver/test_history.py`: `recycle_bench` history has one block with its tear ids, records
    strictly decreasing `residual_max` after the first three iterations (document the actual sequence
    in the test), `iterations == len(records)`; `amine_loop` history reports `wegstein` acceleration.
  - `tests/contracts/test_diagnostics.py`: round-trip JSON; status derivation.
  - `tests/api/test_solve.py`: failed solve → 200 with `errors` populated (extend, do not weaken).
  - All existing solver and e2e tests PASS unchanged; `bench --check` unchanged.

## Method
Behaviour-preserving for converging flowsheets. The e2e slice and golden oracles are the gate.

## Acceptance criteria
- [ ] All tests above PASS; existing tests unchanged; slice byte-identical
- [ ] `openapi.json`, `schema.d.ts` regenerated; `npm run check:api && npm run typecheck` green
- [ ] `bench/baseline.json --check` unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
Design specs (P2-01), tear initialisation (P2-03), the diagnostics UI.
