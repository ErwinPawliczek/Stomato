# P1-13: Column convergence integrity: no false convergence, exact property keys

- **Phase:** Column core. Fixes the mechanism behind #248 (column gates met loosely) and unblocks #332 / draft #333 (exact property-cache keys).
- **Depends on:** S0-1c step 2 (#242) merged, because its shared NS controller is edited here. #333 rebases onto this.
- **Packages you may edit:** `ngdesign.units.column` (`inside_out.py`, `naphtali_sandholm.py`, `specs.py`, the shared controller); `tests/units/column/`, `tests/units/column_shortcut/test_v2_vs_mesh.py`, `tests/units/test_column*.py`; regenerated goldens only as stated below.
- **Never edit:** `thermo/` (the cache fix is #333's), `contracts/`, `amine/`, `scripts/validate_units.py`.
- **Issues:** #248, #332, #157 (P1-12's rectifier basin gap, which exact keys remove).

## Diagnosis (orchestrator, 2026-10-25; probes in the #248 / #333 threads)
1. **Damped inside-out stalls at the sweep cap.** `inside_out._refresh_model` blends the new K-correlation and relative volatility 50/50 with the previous sweep's (`_OUTER_DAMP = 0.5`). That fixes the asymptotic contraction at 0.5 per sweep. The deethanizer reaches M = 4.2e-6 at the 40-sweep cap. Undamped it reaches 4.3e-9 by sweep 22; with damping lifted once the ratio settles at 0.5, 6.3e-9 by sweep 32.
2. **NS accepts steps that worsen the true residual on two-tear columns.** `_ns_try_accept` checks the frozen-row residual unless `live_norm` (`n_tears < 2`). With exact property keys, a trial step took the exact M from 4.2e-6 to 0.997, and it was accepted.
3. **`_at_ns_floor` lets two-tear columns through their 1e-8 gate at M 4.2e-6.** That is false convergence. The deethanizer test asserts only `m_norm <= 1e-5` for this reason.
4. **The rounded property cache** (1e-10 in composition, 1e-6 K, 1e-3 Pa; first-seen value) hid items 2 and 3: trial steps raised inside the residual and were rejected, so the floor bypass "converged".

## Changes (each is a single owner; no tolerance is widened)
1. **Adaptive outer damping.** Keep `_OUTER_DAMP` for the first sweeps. Once the observed residual ratio has settled (state the criterion: for example 3 consecutive ratios within ±0.05 of the damping factor), switch to the undamped refresh, and fall back to damping if a sweep increases M. There is one damping owner: `specs` and `inside_out` currently import their own `_OUTER_DAMP`, so make it a single constant.
2. **Exact-residual acceptance for every column.** In the shared NS controller (post-#242), the live-norm acceptance applies to all tear counts. If #242 already did this, verify it and add the two-tear test below.
3. **`_at_ns_floor` scope.** The floor bypass applies only to zero/one-tear columns, as its docstring already says. A two-tear column that can't meet its gate raises `ColumnConvergenceError` with the measured M and H.
4. **Tests that encoded false convergence:**
   - `test_deethanizer_mesh_converges_under_50_sweeps` asserts the real two-tear gate (M ≤ 1e-8, H ≤ its gate) and states the measured sweep count.
   - The two Kremser / V2 checks that re-flash the reported mid-stage liquid and require two phases use the solve's own K (y/x) or a bubble-point flash instead. A saturated liquid flashed at its own stage T sits on the phase boundary.
   - The rectifier strict-xfails (reflux-ratio and distillate-rate specs) are removed if they pass, and the #157 basin-gap note is closed with the measurement.
   - A new test: a two-tear column NS step that worsens the exact residual is rejected (construct it or capture it).

## Acceptance
- With #333's exact keys merged into this branch (rebase it on top), every column test passes with no tolerance widened, and the six #248 failures are resolved as above.
- Bench: column flash counts are reported. They are expected to drop as fewer sweeps run. Every golden value that moves is measured and explained; states tightening from about 4e-6 to below 1e-8 move values by about 1e-6.
- Gates: ruff, ruff format, `mypy src tests` (strict), lint-imports, bench `--check` (with the new counts recorded), harness `--audit`. CI green.

## Steps (each under about 50 minutes, each ending in a push)
1. Adaptive damping (change 1) plus the deethanizer test (real gate). Measure sweeps and M.
2. Live-norm acceptance for all columns and `_at_ns_floor` scope (changes 2–3), plus the two-tear rejection test.
3. Rebase #333's commit (exact keys) on this branch and fix the Kremser / V2 checks and the rectifier xfails (change 4). Then regenerate the bench and dispatch golden with every moved value explained in the PR body.
