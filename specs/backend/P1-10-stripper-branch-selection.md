# P1-10: One-tear stripper convergence — physical branch selection, no band-floor solutions

- **Phase:** 1 (follow-up from the P1-09 review, PR #125)
- **Depends on:** P1-09 (merged), #124
- **Packages you may edit:** `ngdesign.units.column` (`inside_out.py`, `naphtali_sandholm.py`, `specs.py`, `spec.py`), `tests/units/`
- **Contract change:** no
- **Benchmark delta expected:** none — `column` stays at exactly 4,959 flash-equivalents (two-tear path untouched); the P1-09 absorber, Kremser-proper and MDEA tests pass unchanged

## Goal
P1-09 made feed-determined absorbers correct (balances 1e-8, Kremser within 2 %, the MDEA column with
its exotherm). The reboiled stripper is not done. The P1-09 agent's fixed-boilup map of the
4-stage C1 0.1 / nC4 0.9 stripper at 2 MPa (feed on stage 1, kettle) shows two branches:

| kettle vapour V_N (mol/s) | outcome | stage temperatures |
|---|---|---|
| 28–40 (ratio 0.38–0.54) | "converges" | **all four stages pinned at 270 K = t_band_lo** |
| 37.5, 39 | convergence holes | — |
| 41 | converges via NS, D = 10.23, B = 89.77, ratio 0.457 | **301–377 K (the physical branch)** |
| 42–50 | mesh fails, best M ≈ 1e-2 | — |

The band-floor branch is not a solution of the column: a 2 MPa nC4-rich stripper with a kettle
cannot run colder than its 300 K feed on every stage. The secant from the warm seed lands on it
and the spec tests at ratios 0.3 and 0.5 currently "pass" on it. Two defects, one spec:

1. **A profile on the band limit is a failed mesh, not a converged one.** `_solve_mesh` must
   reject (typed `ColumnConvergenceError`, message naming the stages and the limit) any profile
   with a stage within 1e-6 K of `t_band_lo` or `t_band_hi` at acceptance, for every configuration.
   The band is a trust region for the walk, never a solution. Measure what this does to every
   existing column test and the bench (expected: nothing on the two-tear path, which never touches
   the band).
2. **The one-tear stripper must land on the physical branch.** Find why the inside-out walk from
   the feed-traffic seed descends to the floor on a stripper (the kettle supplies vapour at the
   bottom; the seed's bottom-stage temperature should be the kettle's bubble point of the bottoms
   estimate, not the feed temperature), fix the seed and/or the per-stage Kb anchoring so the walk
   stays above the feed temperature, and make the spec secant robust across the 41–60 mol/s window
   (ratios 0.45–0.8): the failures there (best M ≈ 1e-2) are mesh failures at fixed tear, so they
   are inside-out / NS defects, not secant ones. The P1-09 PR body and the #110 thread hold the
   branch map and the attempted fixes (seed restart, live-norm NS acceptance, 8-sweep cap — the
   last two were rejected for turning converging cases into failures or hiding the floor).

## Tests
- `tests/units/test_column_feed_determined.py`: the stripper tests assert, for ratios 0.3, 0.5 and
  0.8 at N = 4 and for 0.5 at N = 10: convergence, the spec within `_SPEC_TOL`, total and component
  balances 1e-8, **every stage temperature above the feed temperature and below the kettle
  temperature**, no stage within 1 K of either band limit; `component_recovery` 0.95 of C1 to the
  distillate at N = 4. No xfail.
- A new test plants a profile on the band floor and asserts `_solve_mesh` rejects it with the typed
  error naming the stage.
- `tests/units/test_column.py`, the absorber, Kremser-proper and MDEA tests of P1-09: unchanged and
  green; `column` bench exactly 4,959.

## Acceptance criteria
- [ ] All stripper cases above converge on the physical branch; the band-floor guard is in place and documented in `spec.py`
- [ ] Every P1-09 test unchanged and green; bench counts identical on all six cases
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
The staged amine units (P1-06, which follows this spec because its regenerator is a reboiled stripper), rate-based stages.
