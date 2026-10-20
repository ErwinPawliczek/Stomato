# P0-03: One deliverables pipeline module (nothing imports cli)

- **Phase:** 0
- **Depends on:** none
- **Packages you may edit:** `ngdesign.pipeline` (fill the placeholder), `ngdesign.cli`, `ngdesign.export`, `ngdesign.api`, `.importlinter` (delete lines only), `tests/api/`, `tests/e2e/`, `tests/test_pipeline.py`
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
The chain *solved flowsheet → sizers → P&ID → rules to fixed point → routing* lives as private
helpers in `cli.py` (`_sizer_for`, `_run_sizers`, `_rule_set`, `_apply_rules`,
`RELIEF_K_GAS`) and is imported from there by `export.py`, `api/routes_pid.py`,
`api/routes_plot.py`, `api/routes_iso.py`. Two API files re-implement the routed-network chain
(`routes_plot._routed_network`, `routes_iso._routed`). Make `ngdesign.pipeline` the single
library owner; CLI, export and API become callers.

## Files
- Edit: `src/ngdesign/pipeline.py` — public, typed, pure functions:
  - `run_sizers(solved) -> SolvedFlowsheet`
  - `rule_set(solved, *, k_gas: float) -> list[PidRule]`
  - `apply_rules(pid, rules) -> PID` (fixed point, same iteration cap as today)
  - `build_pid(solved, *, k_gas) -> PID` (sizers + builder + rules)
  - `route(pid, layout) -> PipingNetwork`
  - `deliverables(solved, layout, *, k_gas) -> Deliverables` (a small frozen dataclass:
    `solved`, `pid`, `network`) so callers that need several stages compute them once.
  - `DEFAULT_K_GAS = 1.24` with the S-34 docstring note; it is a parameter everywhere else.
  Use `pid_rules.builder._sizer_for` (make it public as `sizer_for` there) rather than keeping
  a second copy.
- Edit: `src/ngdesign/cli.py` — delete the private helpers; call `pipeline`. Output must be
  byte-identical.
- Edit: `src/ngdesign/export.py` — import `_cell`/`_port` replacements: move those two helpers
  into `export.py` itself (they are formatting, not CLI) and have `cli.py` import them from
  `export`. `export` must not import `cli`.
- Edit: `src/ngdesign/api/routes_pid.py`, `routes_plot.py`, `routes_iso.py`,
  `routes_export.py` — call `pipeline`; delete `_routed_network` and `_routed`; the plot-plan
  renderer that currently sits in `routes_plot.py` moves to `src/ngdesign/render/plot_svg.py`
  (render package is allowed; it consumes `PID`/`PipingNetwork` only).
- Create: `tests/test_pipeline.py` — `deliverables()` on the solved slice equals, stage by stage,
  what the CLI wrote before (compare against the committed golden outputs used by
  `tests/e2e/test_slice.py`).
- Edit: `.importlinter` — delete the four `P0-03` lines under *both* contracts.

## Method
Pure refactor. Keep the solve cache in `routes_solve.py` as is. Do not change route paths or
response schemas (`openapi.json` must not change; CI checks it).

## Acceptance criteria
- [ ] `grep -rn "ngdesign.cli" src/ngdesign/` returns nothing outside `cli.py` itself
- [ ] `routes_plot._routed_network` and `routes_iso._routed` no longer exist; one implementation in `pipeline`
- [ ] `cli._sizer_for` no longer exists; one `pid_rules.builder.sizer_for`
- [ ] `tests/e2e/test_slice.py` and all `tests/api/` PASS unchanged; `git diff --exit-code openapi.json` clean
- [ ] `.importlinter` P0-03 lines removed; `uv run lint-imports` 0 broken
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
Async jobs, state store, auth (Phase 3). Changing relief basis logic (`_DEFAULT_BASIS`, Phase 1).
