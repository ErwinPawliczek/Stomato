# P2-03: Per-block tear initialisation and a Broyden option for tears

- **Phase:** 2
- **Depends on:** P2-02 (history records are the oracle)
- **Packages you may edit:** `ngdesign.solver`, `ngdesign.contracts` (`flowsheet.py`: `Flowsheet.solver_options` only), `tests/solver/`, `bench/baseline.json` (update with `--update`; state deltas)
- **Contract change:** yes — `Flowsheet.solver_options`
- **Benchmark delta expected:** `recycle_bench` and the amine loops: fewer tear iterations and flashes (state old → new); `slice`/`column`: none

## Goal
Tears start from the molar-flow-weighted mean of **all** boundary feeds, even for a block that sees one
feed; Wegstein is the only accelerator. Both cost iterations on the amine loops. Initialise each block
from what actually enters it and offer Broyden for stiff loops.

## Files
- Edit `contracts/flowsheet.py`: `Flowsheet.solver_options: SolverOptions = SolverOptions()` with
  `SolverOptions(Model)`: `tear_acceleration: Literal["wegstein","broyden","direct"] = "wegstein"`,
  `max_iterations: int = 100`, `rtol: float = 1e-6` (today's `RTOL`/`MAX_ITERATIONS` become the
  defaults), `wegstein_q_min: float = -5.0`.
- Edit `solver/sequential_modular.py`
  - `_init_guess(block)`: the tear stream's first guess is the molar-flow-weighted mean of the feeds
    entering **that block** (streams whose target is in the block and whose source is outside it or a
    boundary feed), falling back to the global mean, then to the nitrogen default. Composition keys
    restricted to the block feeds' support.
  - Broyden: a bounded Broyden update on the tear vector (Biegler et al. ch. 8; initial Jacobian −I,
    step damped to keep flows ≥ 0 and T, P > 0, reset to direct substitution when the residual grows
    three times in a row). Selected per flowsheet by `solver_options.tear_acceleration`; the history
    record names the acceleration used.
- Tests
  - `tests/solver/test_tear_init.py`: a two-block flowsheet (sweet-gas block + amine block) starts the
    amine block's tear from the amine feed composition (assert the first `TearRecord`'s residual vector
    support), not from the global mean.
  - `tests/solver/test_broyden.py`: `mea_amine_loop` converges with `broyden` in fewer iterations than
    with `wegstein` (state both numbers), to the same streams within `rtol`; `recycle_bench` the same.
  - Existing solver tests and e2e loops PASS; converged results within existing tolerances.

## Acceptance criteria
- [ ] All tests above PASS; existing tests unchanged; slice byte-identical
- [ ] `bench/baseline.json` updated; PR states old → new iterations and flashes per case
- [ ] `openapi.json`, `schema.d.ts` regenerated
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
Simultaneous (EO) solve, tear-set optimisation beyond the current heuristic.
