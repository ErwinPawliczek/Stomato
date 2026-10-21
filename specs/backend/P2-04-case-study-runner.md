# P2-04: Case-study runner — parameter grid → N solves → table

- **Phase:** 2
- **Depends on:** P2-01 (`ngdesign.variables`), B-08 (`case_study` tool to be re-pointed here)
- **Packages you may edit:** `ngdesign.study` (new), `ngdesign.cli` (new `study` command), `ngdesign.api` (new `routes_study.py`; `app.py` one include line), `ngdesign.agent` (only to call `ngdesign.study` from the `case_study` tool), `tests/study/`, `tests/api/test_study.py`, `openapi.json` + `schema.d.ts` (regenerated)
- **Contract change:** yes — new routes
- **Benchmark delta expected:** none

## Goal
"Sweep K-101 discharge pressure from 6 to 9 MPa in 7 steps and show power, cooler duty and dew point"
is one request, not seven manual solves. One runner serves the CLI, the API and the agent.

## Files
- Create `src/ngdesign/study.py`
  - `CaseStudy(Model)`: `id`, `inputs: list[Axis]` with `Axis(address, values: list[float])` (full
    grid over the axes), `outputs: list[str]` (readable addresses), `base: Flowsheet`.
  - `run(study, thermo, *, solver="sequential_modular", warm_start=True) -> StudyResult` with
    `StudyResult(rows: list[StudyRow], failed: list[StudyRow])`, `StudyRow(inputs: dict[str,float],
    outputs: dict[str,float|None], status, iterations, wall_s)`. Runs are sequential and deterministic;
    each case warm-starts from the previous converged tears; a failed case records its `UnitError`s
    (P2-02) and the sweep continues. `to_csv(result)`, `to_markdown(result)`.
- CLI: `ngdesign study <project.json> --input K-101.params.P_out=6e6:9e6:7 --output K-101.power_W
  --output E-101.duty_W --csv out.csv`.
- API: `POST /api/study` body `CaseStudy` (without `base`: the current project) → `StudyResult`.
- Agent: the `case_study` tool calls `ngdesign.study.run` (remove its own loop).
- Tests: `tests/study/test_run.py` (slice sweep of K-101 P_out, monotonic power, a case forced to fail
  by an out-of-range value keeps the sweep going), `tests/study/test_cli.py`, `tests/api/test_study.py`.

## Acceptance criteria
- [ ] All tests above PASS; `openapi.json`/`schema.d.ts` regenerated; `check:api` + `typecheck` green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
Parallel execution (Phase 3 job model), optimisation, charts (frontend).
