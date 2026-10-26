# preflash R2: DEFERRED until the column core solves a condenser-only (rectifier) column with a rate spec

- **Family / package:** refining
- **Levels:** R2 (`planned`, row note "short MESH")
- **Status of this spec:** **DEFERRED, no steps.** A preflash column is a short rectifier:
  - the heated crude enters the bottom stage (flash zone);
  - a few trays sit above it;
  - a partial or total condenser makes light naphtha and/or off-gas;
  - there is no reboiler (optionally stripping steam, which is an S0-1c feature).

  Today's column cannot solve that configuration with the rate spec a preflash needs.

## Why deferred (measured on main, 2026-10-25, script `probe_one.py` cases `pfA`/`pfB`/`pfC`)
The case is a light crude stand-in: C3/nC4/nC5/nC6/nC8/nC10 = 0.05/0.10/0.15/0.20/0.25/0.25, 100 mol/s, flashed at 420 K and 3 bar (VF 0.587), fed to stage 4 of a 4-stage column with no reboiler.

| condenser | spec | result |
|---|---|---|
| partial | `distillate_rate` 25 | `ColumnConvergenceError`: 40 sweeps, NS stalled at M = 4.38, 30.6 s |
| total | `distillate_rate` 25 | did not return within 150 s (killed by the probe's `timeout 150`) |
| total | `reflux_ratio` 1.0 | did not return within 150 s |

This matches the documented rectifier basin gap: `test_rectifier_distillate_rate_spec` is a strict `xfail` pending P1-12 (#157).

Runtime is a second blocker. The R0 `example_case` feeds the full assay slate (about 48 pseudo-components). Issue #234 measured about 44 s for one PT flash of a near-saturated 48-pseudo liquid. The V0 harness solves the example three times (solve plus a two-solve determinism check). An R2 example on the full slate would need either a reduced pseudo set or #234 fixed first.

## What un-defers it
1. P1-12 (#157) merged, so the one-tear rectifier converges on `distillate_rate` and `reflux_ratio`.
2. S0-1c merged (steam feeds, free-water refusal or decant) if the preflash is to take stripping steam.
3. #234 fixed, or a documented reduced-pseudo example case.
4. Then the adapter goes in `refining/preflash_r2.py`:
   - `feed_in` to stage N;
   - `condenser: partial|total`, with `vapor_out` = the condenser vapour (or the distillate for partial) and `liquid_out` = the bottoms;
   - specs `distillate_rate` / `reflux_ratio`.

   The tests would be:
   - the exact total-flow identity;
   - the spec at `_SPEC_TOL`;
   - the phase-state identities (bottoms at its bubble point at the bottom-stage P);
   - the R0 relation: R0 at T = the bottom-stage T of R2 is NOT an identity (one flash vs N stages) and must not be asserted as one.

## Orchestrator note
This is the same column-core issue as `refluxed_absorber` R2, plus the #234 runtime.
