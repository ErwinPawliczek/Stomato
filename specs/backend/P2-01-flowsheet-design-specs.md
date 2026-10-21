# P2-01: Flowsheet-level design specs (Spec / Adjust) with an outer loop around the solver

- **Phase:** 2
- **Depends on:** P2-02 (history and errors), B-08 addresses (`ngdesign.agent.addresses` grammar)
- **Packages you may edit:** `ngdesign.contracts` (`flowsheet.py`: `Flowsheet.design_specs`; new `specs.py`), `ngdesign.solver` (new `design_specs.py`; `sequential_modular.py` only to expose the inner solve), `ngdesign.variables` (new; move `agent/addresses.py` here and re-export from the agent), `tests/contracts/`, `tests/solver/`, `tests/test_variables.py`, `openapi.json` + `schema.d.ts` (regenerated)
- **Contract change:** yes — `Flowsheet.design_specs`, `SolvedFlowsheet.design_spec_results`
- **Benchmark delta expected:** none for existing cases; new case `slice_spec` added (state its numbers)

## Goal
"Set K-101 discharge pressure so the TEG contactor outlet water content is 7 lb/MMscf" is the everyday
design question. Today the engineer iterates by hand. A design spec names a target (any readable
variable), a manipulated variable (any writable one), bounds and a tolerance; an outer loop drives the
sequential-modular solve to the target.

## Files
- Create `src/ngdesign/variables.py` — the address grammar (moved from `agent/addresses.py`, which
  becomes a one-line re-export): `resolve(address, solved) -> float`, `assign(flowsheet, address,
  value) -> Flowsheet` (pure; returns a copy), `readable(solved) -> list[str]`, `writable(flowsheet)
  -> list[str]`. Addresses: `S-003.T|P|molar_flow|mass_flow|vapor_fraction|x.<cid>|y.<cid>`,
  `K-101.duty_W|power_W|info.<key>|params.<key>`, `S-001.feed.T|P|molar_flow|composition.<cid>`.
- Create `src/ngdesign/contracts/specs.py`
  - `DesignSpec(Model)`: `id`, `target: str` (readable address), `value: float`, `manipulated: str`
    (writable address), `lower: float`, `upper: float`, `tolerance: float = 1e-4` (relative on the
    target), `max_iterations: int = 30`.
  - `DesignSpecResult(Model)`: `id`, `achieved: float`, `manipulated_value: float`, `iterations`,
    `converged: bool`, `history: list[tuple[float, float]]` (manipulated, target per iteration).
- Edit `contracts/flowsheet.py`: `Flowsheet.design_specs: list[DesignSpec] = []` (validator: ids unique,
  addresses parse, `lower < upper`); `SolvedFlowsheet.design_spec_results: list[DesignSpecResult] = []`.
- Create `src/ngdesign/solver/design_specs.py` — `solve_with_specs(fs, thermo, inner) ->
  SolvedFlowsheet`: for one spec a bounded secant (bracket from `lower`/`upper`, bisection safeguard,
  Brent when the bracket straddles); for several specs a bounded Broyden on the vector of manipulated
  variables with the Jacobian seeded by one-sided finite differences (step 1 % of the range). Each
  outer iteration calls the inner SM solve once (the inner tear loop starts from the previous solve's
  tear values — expose `SequentialModular.solve(fs, thermo, warm_start=...)`). A failed inner solve
  (`status="failed"`) aborts with the partial result and `converged=False` on the spec.
- Register `@register("solver", "sequential_modular")` to run specs automatically when
  `fs.design_specs` is non-empty (the registered solver is the outer one; the inner stays importable).
- Bench: add case `slice_spec` (the slice with one spec: `K-101.params.P_out` so that
  `S-00x.x.H2O` of the contactor gas out equals its current value × 0.9) to `scripts/bench_baseline.py`.
- Tests
  - `tests/test_variables.py`: every readable/writable address on the solved slice; unknown address
    error names the nearest valid ones; `assign` is pure.
  - `tests/solver/test_design_specs.py`: (1) slice with the spec above converges within tolerance in
    ≤ 12 outer iterations and the manipulated value is inside the bounds; (2) a target outside the
    reachable range ends `converged=False` with the closest achieved value and both bracket ends in
    `history`; (3) two specs (K-101 P_out → water content, E-101 T_out → separator vapour fraction)
    converge with Broyden in ≤ 20 iterations; (4) a spec whose inner solve fails returns the partial
    result; (5) determinism: two runs byte-identical.
  - `tests/contracts/test_specs.py`: validation (bad address, lower ≥ upper, duplicate id).

## Method
Cite Biegler, Grossmann & Westerberg, *Systematic Methods of Chemical Process Design* ch. 8 (design
specifications, Broyden) in docstrings. Warm starts are the point: without them each outer iteration
re-converges every recycle from the global mean.

## Acceptance criteria
- [ ] All tests above PASS; existing tests unchanged; slice byte-identical when `design_specs` is empty
- [ ] `openapi.json`, `schema.d.ts` regenerated; `npm run check:api && npm run typecheck` green
- [ ] `bench/baseline.json`: existing cases unchanged; `slice_spec` added with its numbers in the PR
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
Equation-oriented solve, optimisation, the UI for specs, the `Adjust` on unit-internal variables.
