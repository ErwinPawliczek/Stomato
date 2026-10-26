# refluxed_absorber R2: DEFERRED until the column core solves condenser-only and reboiled-absorber configurations

- **Family / package:** column
- **Levels:** R2 (`planned`), the row's only level
- **Status of this spec:** **DEFERRED, no steps.** The level cannot be delivered as an adapter over today's column API. It needs core column work in `src/ngdesign/units/column/`, which S0-1c owns now, plus P1-12 (#157, warm-chained tear continuation).
- **Branch / issue:** none until un-deferred.

## Why deferred (measured on main, 2026-10-25, script `probe_one.py`)
The row's note says "MESH with one end exchanger (the configurations exist; tests are missing)". The configurations parse, but they do not converge on a representative refluxed or reboiled absorber. The case: gas C1/C2/C3 = 0.8/0.1/0.1 at 300 K, 2 MPa, 100 mol/s; lean nC5 40 mol/s on stage 1; 4 stages.

| configuration | spec | result |
|---|---|---|
| partial condenser, no reboiler (refluxed absorber), gas on stage 4 | `distillate_rate` 95 | `ColumnConvergenceError`: 40 inside-out sweeps, NS fallback stalled at M = 8.85, 14.9 s |
| no condenser, kettle (reboiled absorber), gas on stage 2 | `boilup_ratio` 0.3 | `ColumnConvergenceError`: NS stalled at M = 7.12, 32.1 s |
| no condenser, kettle (reboiled absorber), gas on stage 2 | `bottoms_rate` 45 | `ColumnConvergenceError`: NS stalled at M = 1.05, 32.1 s |

The existing tests cover the one-tear rectifier only for a dew-point binary vapour feed with a `reflux_ratio` spec. The same rectifier with a `distillate_rate` spec is a strict `xfail` pending P1-12 (#157), in `tests/units/test_column_feed_determined.py::test_rectifier_distillate_rate_spec`: "basin gap … warm-chained tear continuation is P1-12".

An adapter over these configurations would ship a level that refuses on ordinary inputs. Per the U-R2 conventions it stays `planned`.

## What un-defers it
1. P1-12 (#157) warm-chained tear continuation merged, so one-tear rectifiers converge on `distillate_rate`.
2. A column-core fix (S0-1c owner) for the two-feed reboiled absorber. The likely cause is the seed: the zero/one-tear `_seed_profile` assumes the feed traffic of a single-feed column.
3. Then this spec is rewritten as an adapter in `column_shortcut/refluxed_absorber_r2.py`. It would have the absorber R2 shape (gas on stage N or a middle stage, solvent on stage 1) plus `end_exchanger: condenser | reboiler`. The closed-form tests would be the rate-spec material identity at `_SPEC_TOL` and the phase-state identities, like `reboiled_stripper` R2.

## Orchestrator note
Treat these three measured failures as one column-core issue. A probe script reproducing them is at `scratchpad/unit-specs/probe_one.py` (cases `rflxA`, `rflxB`, `rflxC`).
