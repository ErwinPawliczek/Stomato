# P1-09: Column configurations with zero or one tear (absorbers, strippers) and amine states inside the column

- **Phase:** 1 (follow-up from the P1-06 BLOCKED report, issue #98)
- **Depends on:** P1-03 (`units/column/` package), P1-04 (`amine_ke` / `amine_enrtl`), P1-08
- **Packages you may edit:** `ngdesign.units.column` (`spec.py`, `inside_out.py`, `naphtali_sandholm.py`, `specs.py`, `thermo_adapter.py`, `__init__.py`), `ngdesign.amine` (`package.py` only, items E1–E2), `tests/units/`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none — the `column` case stays at exactly 4,959 flash-equivalents (it is a two-tear column and must take the unchanged path); state the before/after numbers in the PR

## Goal
`_parse_params` accepts `condenser="none"` and `reboiler="none"` and even counts the degrees of
freedom correctly (`n_tears` = 0 for a feed-determined absorber, 1 for a reboiled stripper or a
rectifier without reboiler), but the solver underneath only ever ran two-tear columns: every test in
`tests/units/test_column.py` has a total condenser and a kettle. The orchestrator reproduced the
P1-06 report on plain Peng–Robinson (C1/nC4 gas into lean nC4, 2 MPa, 300 K, 2/4/8 stages): every
case raises `ColumnConvergenceError`. The causes, all in `units/column/`, are structural, not
tuning:

1. **Phantom tears.** `specs._initial_tears` returns `(0.5 F, 0.8 F)` for every configuration.
   `_apply_tears` ignores them for absent hardware, but `inside_out._mesh_v`, `_inner_solve` and
   `_naphtali_sandholm` pin `V[n-1] = t_bot_tear` whenever the value is not `None`, while
   `_v_free_indices` leaves `V[n-1]` free for `reboiler="none"`. The stage-N energy balance can
   then never close (the 2-stage absorber ends at H = 1.13e-2 against the 1e-2 gate with M at
   8e-11). The error message literally reports `tears (65.0, 104.0)` for a column that has none.
2. **No zero/one-tear control path.** With absent tears set to `None` (orchestrator experiment,
   one-line patch of `_initial_tears`), `_solve_specs` fails in new ways: a secant over an empty
   free-tear vector (`max() iterable argument is empty`), `ColumnSpecError("column spec tears
   unresolved before secant solve")` for a one-spec stripper, and `mesh_at` "backtracks" tears
   that do not exist.
3. **Seed built for a distillation column.** `_seed_profile` assumes `d = 0.35 F`, a vapour profile
   falling from `2.5 d` to `1.5 (F − d)`, and `x = y = z` (the *mixed* feed composition) on every
   stage; `_temperature_seed` scans the mixed feed. An absorber has the gas on stage N and the
   solvent on stage 1: V ≈ gas feed and L ≈ solvent feed on every stage, the temperatures lie
   between the two feed temperatures, and the mixed composition (C1 0.65 / MDEA 0.03 / CO2 0.05)
   is a state the amine package cannot evaluate as a liquid. Experiment: with tears fixed the
   zero-tear mesh still fails (singular tridiagonal at 8 stages, NS budget at 4, M = 1 at 20).
4. **Error leakage.** The Naphtali–Sandholm line search evaluates trial states without clamping
   T to `t_band_lo..t_band_hi` (trials reached ~100 K) and only catches `ColumnConvergenceError`;
   a `ValueError` from the thermo escapes `_solve_mesh` as a raw exception.
5. **Amine package on column-internal states.** `_equilibrium_internal`'s loading fixed point
   raises after `_LOADING_MAX_ITER` on solvent-lean mixed overalls, and the speciation root
   bracket is fixed, so a far-off trial temperature raises `root not bracketed` from
   `brent_root` instead of a typed error the column can treat as a rejected step.

## Files and deliverables
- `specs.py` / `spec.py`: **A. Tear bookkeeping by configuration.** `_initial_tears` returns
  `tuple[float | None, float | None]` with `None` for absent hardware; `_Column` carries
  `n_tears`; `_solve_specs` has explicit paths for 0 free tears (no specs → one mesh solve, no
  secant), 1 free tear (bounded 1-D secant on the only spec) and 2 (unchanged). `mesh_at`
  backtracks only tears that exist. `_check_spec_feasibility` and every existing
  `ColumnSpecError` message stay as they are.
- `inside_out.py`, `naphtali_sandholm.py`: **B. Pin only what is a tear.** `V[n-1]` is written
  from the bottom tear only when `reboiler == "kettle"`; `V[0]` only for a partial condenser;
  `_v_free_indices`, `_h_equation_stages`, `_mesh_v`, `_inner_solve`, `_pack_state`/`_apply_state`
  and the NS residual function agree on this through one helper, not four copies of the rule.
- `inside_out.py`: **C. Configuration-aware seed.** When the column has no condenser or no
  reboiler, build the seed from the feeds' flashed phase flows: `V_j` = vapour feed flow entering
  at or below stage j, `L_j` = liquid feed flow entering at or above stage j (both floored at
  `_FLOW_FLOOR`), `x_j` = the nearest liquid feed's composition, `y_j` = the nearest vapour
  feed's composition, `T_j` linear between the stage-1 feed temperature and the stage-N feed
  temperature (or the single feed's T ± 10 K). Two-tear columns keep the existing seed exactly
  (the `column` bench count is the proof). The temperature band `t_band_lo/hi` for these columns
  is `[min feed T − 30 K, max feed T + 80 K]` (absorption exotherm headroom), not the pure-component
  extremes.
- `inside_out.py`, `naphtali_sandholm.py`: **D. Convergence and containment.** Whatever
  inside-out damping / NS budget change the acceptance cases need, documented with measured sweep
  counts in the PR (the `_MESH_*` tolerances stay). NS line-search trial states are clamped to the
  band; a `ValueError` or `SaturationError` raised by the thermo during a trial step rejects the
  step like a `ColumnConvergenceError` does today. The only exceptions that leave `Column.solve`
  are `ColumnSpecError` and `ColumnConvergenceError`; the latter's message carries the best
  profile's M and H residuals and the sweep/NS pass counts.
- `amine/package.py`: **E1.** `_equilibrium_internal` converges on solvent-lean mixed overalls
  (under-relax the loading update when it oscillates; keep the 1e-12 tolerance and the iteration
  cap, raise `ValueError` with z, T, P in the message only if it still fails). **E2.** The
  speciation root finders raise a typed `AmineChemistryError(ValueError)` naming T and the
  bracket when the chemistry window is left, never a bare `root not bracketed`. No change to any
  converged number: `tests/thermo/test_amine_package.py`, `tests/units/test_amine_units*.py`,
  `tests/e2e/test_amine_loop.py`, `test_mea_amine_loop.py` and the `amine_loop` /
  `mea_amine_loop` bench counts are unchanged.

## Tests (new)
- `tests/units/test_column_absorber.py` (plain `pr`):
  1. Feed-determined absorber, `condenser="none"`, `reboiler="none"`, gas 100 mol/s C1 0.9 / nC4
     0.1 at 300 K, 2 MPa on stage N, lean nC4 30 mol/s at 300 K on stage 1, for N = 2, 4, 8, 20:
     converges; overall and per-component balances close to 1e-8 relative; energy balance closes
     to 1e-6 relative on the boundary streams; nC4 recovered to the bottoms increases
     monotonically with N; the bottoms leaves warmer than the lean feed (absorption exotherm).
  2. Kremser oracle (Kremser 1930; Seader, Henley & Roper ch. 5, eq. 5-48/5-50): for N = 4 and
     the converged mid-column absorption factor A = L/(K V), the fraction of nC4 absorbed agrees
     with the Kremser equation within 10 %. State the measured value.
  3. Reboiled stripper, `condenser="none"`, `reboiler="kettle"`, feed C1 0.1 / nC4 0.9 at 300 K,
     2 MPa on stage 1, N = 4 and 10, one spec: `boilup_ratio=0.5` and separately
     `component_recovery` of C1 to the distillate 0.95 — converges, spec met within `_SPEC_TOL`,
     balances as in (1).
  4. Rectifier without reboiler, `condenser="total"`, `reboiler="none"`, saturated vapour feed on
     stage N, one spec `reflux_ratio` plus the required rate pin (`distillate_rate`), N = 6:
     converges, balances as in (1).
  5. Every failure path is typed: a stripper with two specs raises `ColumnSpecError`; a column
     pushed outside its band (e.g. absorber lean feed at 150 K) raises `ColumnConvergenceError`
     carrying residual numbers, never a bare `ValueError`.
- `tests/units/test_column_amine.py`: the `MdeaAbsorber.example_case()` gas and lean amine feeds
  on a 20-stage feed-determined column with `amine_ke` converge; outlet CO2 mole fraction is below
  the inlet's; rich CO2 loading exceeds lean loading; max stage T − lean inlet T in [0, 30] K;
  per-component balances 1e-8. Mark the same case with `amine_enrtl` `xfail(strict=False)` if
  it does not converge and say why in the PR.
- `tests/thermo/test_amine_package.py` additions: the overall z = {C1 0.65, H2O 0.274, MDEA 0.03,
  CO2 0.046} at 320 K / 5 MPa flashes on `amine_ke` without raising and returns a two-phase or
  vapour state; a speciation call at 100 K raises `AmineChemistryError`.
- `tests/units/test_column.py` and `tests/golden/` PASS unchanged.

## Method
Boston & Sullivan inside-out (1974) and Naphtali & Sandholm (1971) as already implemented; the
absorber seed follows the standard absorber initialisation (Seader ch. 10.3: constant molar flows
equal to the feed flows, linear temperature profile between the feed temperatures). Kremser for
the oracle. All SI. No new solver family: fix the existing one's bookkeeping, seed and containment.

## Acceptance criteria
- [ ] All new tests PASS; `tests/units/test_column.py` PASS unchanged; `bench/baseline.json --check` passes with every case unchanged (`column` exactly 4,959)
- [ ] One helper decides which vapour flows are tears (grep shows no per-module copies of the kettle/partial rule)
- [ ] `grep -rn "root not bracketed" src/ngdesign/amine` only in `roots.py`
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
The staged amine units themselves (P1-06, which depends on this spec), Murphree efficiencies, new
spec kinds (`component_ratio` stays in P1-06), reflux return to a stripper, rate-based stages.
