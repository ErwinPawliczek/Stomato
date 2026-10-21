# P1-08: One saturation solver over a vapour-fraction callable

- **Phase:** 1 (follow-up from the P1-04 review)
- **Depends on:** P1-01, P1-04
- **Packages you may edit:** `ngdesign.thermo` (`_state.py`, new `saturation.py`), `ngdesign.amine` (`package.py` only to call the shared solver), `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none (saturation is not on any bench path); state the saturation test timings before/after

## Goal
`thermo/_state._saturation` (P1-01) and `amine/package._boundary` + `_scan_to_plateau` +
`_bisect_predicate` (P1-04) implement the same plateau-scan-then-bracket algorithm twice with different
tolerances and bracket rules. One solver, parameterised by a `vf_at(x) -> float` callable and the Wilson
bounds, serves both packages and any future one.

## Files
- Create `src/ngdesign/thermo/saturation.py`: `solve_saturation(vf_at, *, kind, unknown: Literal
  ["P","T"], bounds: tuple[float, float], rel_tol=1e-8, max_iter=60, plateau_eps=1e-6, scan=1.3) ->
  float` with the P1-01 semantics (scan the plateau end, tighten the other end, bracketed secant with
  bisection safeguard) and `interior_vf_solve(vf_at, target, lo, hi)` for TVF/PVF. Docstring cites
  Michelsen & Mollerup ch. 10 and the P1-01 findings (Wilson bounds past Tc, plateau tolerance).
- `_state._saturation` and `_state._secant_solve` become thin wrappers that build `vf_at` from
  `_pt_phase_pairs`; `amine/package._boundary` builds it from `_equilibrium_internal`. Delete the
  duplicated helpers.
- Tests: `tests/thermo/test_saturation.py` and `test_amine_package.py` PASS unchanged (bit-identical
  results on the pure fluids and the C1/C3 binary; state any last-digit differences); a new
  `tests/thermo/test_saturation_solver.py` exercises the solver on an analytic `vf_at` (piecewise linear
  with plateaus) including the degenerate cases (target at a bracket end, no plateau → `SaturationError`).

## Acceptance criteria
- [ ] One definition of the plateau scan and the bracketed secant under `src/ngdesign/` (grep)
- [ ] All existing saturation and amine tests PASS unchanged; golden thermo unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
