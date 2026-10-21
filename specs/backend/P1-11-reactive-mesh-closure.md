# P1-11: Reactive-package column mesh closure — smooth K-values, converged stages

- **Phase:** 1 (follow-up from the P1-06 BLOCKED report, issue #98)
- **Depends on:** P1-09 (merged #125), P1-10 (merged #149), the amine Rachford–Rice hotfix (`(1 − β) + βK` denominator, main)
- **Packages you may edit:** `ngdesign.amine` (`package.py`, `kent_eisenberg.py`, `enrtl.py`, `roots.py`), `ngdesign.units.column` (`spec.py`, `specs.py`, `inside_out.py`, `naphtali_sandholm.py`), `tests/thermo/`, `tests/units/`
- **Contract change:** no
- **Benchmark delta expected:** none on `slice`, `slice_spec`, `recycle_bench`, `column` (non-reactive paths untouched: 13 / 65 / 515 / 4,959 flash-equivalents exactly). `amine_loop` (31) and `mea_amine_loop` (45) run the shortcut units, not the column, and must stay identical too: a flash-count change there means the package's flash path changed, which this spec forbids.

## Goal
The staged amine units (P1-06) are blocked by the column, not by the units. On the reactive
package the zero-tear 20-stage MDEA absorber converges to the right physics (CO2 slip 3.6e-4,
rich loading 0.502, bulge 314.3 K — P1-09) but the mesh stagnates at stage residuals
M ≈ 5e-3 (gate `_MESH_M_TOL_REACTIVE = 1e-2`), and those accepted residuals propagate into the
boundary streams: component closure ≈ 1.8e-3 relative (C1 −0.34 mol/s, H2O +0.30 mol/s on a
192 mol/s feed). The locked property test `tests/property/test_unit_balances.py` requires
1e-6·total for every registered unit, so no staged amine unit can register until the reactive mesh
closes like the non-reactive one (P1-09 absorbers: 1e-8…1e-12; P1-10 strippers: 1e-6).

The P1-09 note in `units/column/spec.py` records *why* it stagnates: the inside-out
`ln Kb = A + B/T` anchoring tracks the reactive acid-gas K-values' temperature dependence but not
their composition (loading) dependence, and the Naphtali–Sandholm fallback walks M **uphill**
(5.2e-3 → 4.1e-1 over 30 passes) because "the reactive K evaluation is too noisy for
finite-difference derivatives". Newton on a smooth residual does not walk uphill. So the defect is
upstream of the column: the package's K-value surface is not smooth (or not deterministic) at the
scale of the FD step, and the column's reactive gate papers over it. Fix it at the source, then
remove the paper.

## Method
1. **Measure the K-value surface first.** Write a probe (keep it as a test, `tests/thermo/test_amine_k_smoothness.py`) that evaluates `amine_ke` K-values, `flash_pt` phase split and enthalpies on the P1-09 MDEA absorber's stage states (take the converged 20-stage profile from `tests/units/test_column_feed_determined.py`'s MDEA case: T 281–315 K, loadings 0.0–0.5) and reports, for each stage and each component, the central finite-difference derivative dK/dT and dK/dx_CO2 at steps h = 1e-2, 1e-3, …, 1e-7 (relative). A smooth function gives derivatives that converge as h shrinks until round-off (≈ 1e-8 relative for an evaluation accurate to 1e-16); a noisy one gives derivatives that *diverge* as h shrinks. Record the step at which each derivative stops converging — that is the noise floor the NS Jacobian sees. Candidate sources, in order of likelihood (verify, do not assume): the `_LOADING_MAX_ITER = 50` loading loop returning its `best` non-converged state (a hidden discontinuity), the `max(x_i, 1e-12)` and `_MAX_LOADING` clamps, the `_ALL_VAPOR_K` switch at `k <= 0`, the speciation root's bracket tolerance in `kent_eisenberg.py` / `enrtl.py` (`brent_root` xtol) and any `min`/`max`/`abs` kinks inside the speciation residual, and the Henry's-law and Psat correlations crossing table boundaries.
2. **Make the surface smooth and deterministic to 1e-10 relative** at every source found in step 1, in `ngdesign.amine`: a converged loading iteration (raise or tighten, never "best"), continuous clamps (none inside the physical window), speciation roots solved to machine precision, no branch switches inside the applicability window. The package's *values* must not change beyond the former noise: `tests/thermo/test_amine_package.py`, `tests/units/test_amine_units_package.py`, both e2e amine loops and their bench flash counts stay identical — if a bench count moves, the flash path moved, stop and report.
3. **Make the exact gate equilibrium-consistent (revised 2026-10-21 after the step-1/2 report on
   #153).** `_exact_residuals` closes the component balances with the profile's stored y and never
   checks y = K(T, x)·x, so an inside-out profile whose anchor-built y is 2.5 decades off the
   package's K reads as converged at M ≈ 5e-3 while the true MESH residual is ≈ 0.49 (measured
   MDEA absorber). The gate evaluates the balances with y_ij = K_ij(T_j, x_j)·x_ij from the live
   package (refresh y before the balance, or add the E-residual; one owner, the number NS sees).
   The same definition serves every package (no per-package branch). Ruling 2026-10-21 16:20: the
   honest gate crosses 1e-8 one to three sweeps later on non-reactive columns, so the `column` bench
   baseline moves 4959 → 6508 flash-equivalents with byte-identical products (`--update` for that
   case only, trace in the commit); every other bench case and every P1-09/P1-10 test identical. The P1-09 MDEA assertions become `xfail(strict=True)` with the measured residual
   until the mesh closes.
4. **Then close the mesh with Naphtali–Sandholm on the smooth surface.** First suspect: the FD
   Jacobian step `delta = max(|u|·1e-7, 1e-9)` sits below the smoothness floor step 1 certified
   (h = 1e-6 relative), so the Newton direction is noise and the line search rejects every trial.
   Measure a reactive stage's FD Jacobian column at 1e-5/1e-6/1e-7 against the step-1 derivative,
   raise the step to the certified floor (relative, scale-aware, central differences if needed),
   confirm the `_unpack_t` band clamp and the x ≥ 0 clamp are inactive, and run NS from the
   inside-out best state. Lower `_MESH_M_TOL_REACTIVE` only to a floor NS actually reaches, with the
   measurement in `spec.py`. Continuation on the reaction strength (a package knob, contract change)
   is allowed only if NS descends but stalls far from the solution — measured first.
5. **The regenerator.** Its seed is mass-consistent (M ≈ 1e-16) and energy-inconsistent (H ≈ 0.07);
   the inside-out energy walk diverges from it and Kb re-anchoring does not help (measured,
   reverted). Once NS descends, extend the P1-10 NS-first path to reactive one-tear kettles, start
   from that seed, measure the profile it lands on (expect 380–400 K at 1.9 bar for 50 wt % MDEA)
   and set the trust-band ceiling from the measured kettle, keeping `_reject_band_limit`.

## Tests
- `tests/thermo/test_amine_k_smoothness.py`: for both packages, every stage state above: FD derivatives converge monotonically down to h = 1e-6 relative with the final two steps agreeing within 1e-4 relative (document the measured floor); two evaluations at the same state are bit-identical.
- `tests/units/test_column_feed_determined.py`: the MDEA absorber case additionally asserts boundary component and total balances ≤ 1e-6·feed (target 1e-8; record the measured number), and its P1-09 anchors (slip, loading, bulge) hold within the tolerances already there.
- `tests/units/test_column_amine.py` (or a new file): a 20-stage reboiled MDEA regenerator at 1.9 bar with `boilup_ratio` 0.1 (measure a physical ratio; Kohl & Nielsen ch. 2 MDEA reboiler duty ≈ 0.9–1.4 lb steam / lb acid gas) converges on the physical branch (stages between the feed temperature and the kettle, none on a band limit), boundary balances ≤ 1e-6, lean loading below the rich loading, and the kettle vapour is mostly water (y_H2O > 0.9). No `ZeroDivisionError`, no raw exceptions: only typed `ColumnConvergenceError` / `AmineChemistryError`.
- Every existing amine, column, e2e and property test green and unchanged; bench identical on all six cases.

## Acceptance criteria
- [ ] Smoothness test green with the measured floor documented in `package.py`
- [ ] Exact gate equilibrium-consistent for every package; `column` baseline updated to the measured count with the trace, all other bench cases byte-identical
- [ ] MDEA absorber boundary balances ≤ 1e-6 relative; `_MESH_M_TOL_REACTIVE` lowered to the measured floor (or deleted) with the measurement in `spec.py`
- [ ] Reboiled MDEA regenerator converges on the physical branch with the test above
- [ ] Bench counts identical on all six cases; ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
The staged amine units themselves (P1-06 follows this spec), rate-based stages, eNRTL H2S service, new spec kinds (P1-06 owns `component_ratio`).
