# P0-06: Benchmark baseline (flash count + wall time) tracked in CI

- **Phase:** 0
- **Depends on:** none
- **Packages you may edit:** `scripts/`, `bench/` (new, committed), `tests/bench/`, `.github/workflows/bench.yml` (new file only — do not edit `ci.yml`)
- **Contract change:** no
- **Benchmark delta expected:** this spec *creates* the baseline

## Goal
Phase 1 claims "column solves with ≤ 10 % of today's flash count" and "ms per flash tracked".
Nothing measures that today. Give every PR a number: flashes and wall time per benchmark
flowsheet, compared against a committed baseline.

## Files
- Create: `src/ngdesign/bench/__init__.py` is **not** allowed (no engine change). Instead:
- Create: `scripts/bench_baseline.py`
  - A `CountingThermo` proxy that wraps any `Thermo` plugin and counts `flash_pt/ph/ps` calls
    (and total wall time inside them). Obtained by `registry.create("thermo", name)` then
    wrapping; passed to the solver like any thermo.
  - Cases (reuse `scripts/bench_cases.py` where it already defines them): `slice`,
    `recycle_bench` (`flowsheets/recycle_bench.py`), `amine_loop`, `mea_amine_loop`, and the
    column `example_case()` solved standalone.
  - Output `bench/baseline.json`: per case `{flashes_pt, flashes_ph, flashes_ps, flash_wall_s,
    total_wall_s, solver_passes, converged}` plus `{python, platform, commit}` metadata.
  - `--check`: re-run and exit non-zero if any case's flash count exceeds baseline by > 2 %
    (flash counts are deterministic) or wall time exceeds by > 50 % (noisy; generous).
    `--update` rewrites the baseline.
- Create: `bench/baseline.json` — generated on the PR's machine from `main`; the PR says the
  machine and the command.
- Create: `.github/workflows/bench.yml` — on `pull_request`, backend-changes only: `uv sync`,
  `uv run python scripts/bench_baseline.py --check`, and post the per-case delta table as a
  step summary (`$GITHUB_STEP_SUMMARY`). Fails only on the flash-count rule.
- Create: `tests/bench/test_counting_thermo.py` — the proxy counts correctly and is transparent
  (same `StreamState` as the wrapped plugin).

## Method
No engine code changes. The proxy must satisfy `contracts.plugins.Thermo` (`runtime_checkable`).
Flash wall time is measured inside the proxy with `time.perf_counter`.

## Acceptance criteria
- [ ] `uv run python scripts/bench_baseline.py --check` passes on main and prints the table
- [ ] `bench/baseline.json` committed with all five cases and metadata
- [ ] Column case reports its flash count (expected order 10^3–10^5) — state the number in the PR
- [ ] `tests/bench/test_counting_thermo.py` PASS
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; `.github/workflows/ci.yml` untouched
- [ ] Nothing outside the listed paths changed

## Out of scope
Making anything faster. Changing the solver or units to expose iteration counts beyond what
`SolvedFlowsheet` already reports.
