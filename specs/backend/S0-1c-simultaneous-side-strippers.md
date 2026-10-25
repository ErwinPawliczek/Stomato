# S0-1c: Side strippers and free water solved simultaneously with the main column

- **Phase:** Unit catalogue round 2 (slice S0). It replaces the nested-tear design of PR #239 (closed, superseded) for S0-1 features 2-3.
- **Depends on:** S0-1 part 1 (#238, pumparounds, merged).
- **Packages you may edit:** `ngdesign.units.column` (`spec.py`, `specs.py`, `inside_out.py`, `naphtali_sandholm.py`, `linalg.py`, `__init__.py`, new modules inside the package); `tests/units/column/` (new files, plus `test_unimplemented_refusals.py`); generated `docs/units*`.
- **Never edit:** `contracts/`, `thermo/`, `amine/`, `solver/`, `scripts/validate_units.py`, `units/catalogue.py`, `units/levels.py`, the refining package, `tests/property/`, `data/unit_models/` (the catalogue flip is S0-1 part 2c).
- **GitHub issue:** #235
- **Contract change:** no.
- **Benchmark delta expected:** none. A column with no `side_strippers` and no `condenser_water_decant` must run today's code path exactly: the bench and the byte-identical dispatch golden are the regression gate on every step.

## Why (ruling, 2026-10-25)
PR #239 coupled each stripper to the main column through an outer secant on tear variables: draw, return flow, return T and return composition. Diagnosis (PR #239 comments) found:
1. The cold standalone stripper solve fails for strongly superheated steam and near-zero vapour traffic.
2. The component list changed between evaluations.
3. The outer stops sit below the inner solves' reproducibility floor, which is structural to any nested design.
4. At S0-3 scale (about 25 species, 3 strippers) there are about 81 tears, so a single finite-difference Jacobian costs about 82 crude-column solves, which takes hours.

The standard formulation (RadFrac/PetroFrac, Russell 1983) solves the stripper stages as extra stages of one equation system, linked by internal streams, with one tolerance and no tears. #238's pumparounds are already this kind of link.

## Design
- **Stage graph.** `_Column` gains optional sections:
  - The main stages `1..N` are numbered as today, top to bottom.
  - Each side stripper `s` appends `n_stages` stages, top to bottom.
  - Each stripper adds two **interlinks**:
    - liquid from main stage `draw_stage` to the stripper's top stage, with its flow an unknown (or a spec tear);
    - all vapour leaving the stripper's top stage goes to main stage `return_stage`, carrying its own composition and enthalpy. Pressure let-down is isenthalpic, so no extra term is needed.
  - The stripper's bottom liquid is a product. Steam is an ordinary feed to the stripper's bottom stage; the alternative is a stripper reboiler duty on that stage.
  - A column with no sections builds exactly today's `_Column`.
- **Fixed component list.** Water from steam is part of `col.comps` from the start, so every evaluation uses one component list.
- **Free water.** On any stage where liquid water would separate as a phase (ask the package for a second liquid phase, or compare the water fugacity with that of pure liquid water), refuse with a typed `ColumnSpecError` naming the stage. The exception is the condenser with `condenser_water_decant` on (step 4). The model must never silently report a liquid hydrocarbon carrying 12% dissolved water.
- **Solvers:**
  - Inside-out over the graph is the primary path, with Naphtali-Sandholm as the fallback.
  - The NS Jacobian for graph columns uses stage-coloured finite differences: perturb, at once, the variables of all stages that share no residual. Stages more than two links apart in the graph share a colour. Solve with `scipy.sparse` LU.
  - The dense pure-Python path stays, unchanged, for linear columns.
- **Specs.** A stripper's `product_rate_mol_s` is an ordinary spec row in the existing spec loop, paired with the draw-flow tear. The column keeps its two classic specs.

## Steps: one PR each, in order, each under about one hour of implementer work
Implementer threads are cut off after about an hour: push after every sub-step. A step that does not fit continues through time-boxed fix rounds on the same PR.

1. **S0-1c-1 Topology and parsing.**
   - Stage graph and interlinks in `_build_column`, plus the fixed component list.
   - `side_strippers` and `condenser_water_decant` parsing and validation, salvaged from the PR #239 branch `s0-1b/column-extensions-2` (`spec.py`) together with its typed refusals.
   - A solve that requests strippers still refuses with "not implemented (S0-1c step 3)".
   - Tests: parsing refusals; a graph built for 2 strippers has the expected stage count and links; linear columns byte-identical.
2. **S0-1c-2 Graph Naphtali-Sandholm.**
   - Residuals over the stage graph, including interlink terms.
   - Stage-coloured FD Jacobian plus `scipy.sparse` LU.
   - Tests: on a linear column, the graph-NS result equals the dense NS result to 1e-10. The number of residual evaluations per Jacobian is bounded by the colour count, not the unknown count; the bound is asserted.
3. **S0-1c-3 Stripper solve.**
   - Sequential-section initializer: the main column with a plain side draw, then each stripper standalone fed by that draw, give the starting profile.
   - Inside-out over the graph, with graph-NS fallback.
   - Steam and reboiled strippers; the stripper `product_rate_mol_s` spec.
   - Whole-unit boundary accounting: in = feeds + steam; out = D + B + side draws + stripper products (+ decant); duties = Qc, Qr, the pumparound duties and the stripper reboiler duties. Salvage this from PR #239 items 1-2.
   - Acceptance:
     - identity: a 0-stage stripper equals a plain liquid side draw (1e-10), and zero steam changes nothing;
     - mass, component and energy closure of the whole unit at 1e-8, with enthalpies recomputed independently from thermo;
     - a bit-identical rerun;
     - a steam-robustness grid on a realistic case (nC8/nC10/nC12 at about 2 bar, liquid at its bubble point, 4-stage stripper, steam 0.3, 0.5, 1.0, 1.5 and 2.0 mol/s at 450 K and 550 K). It must converge everywhere, or refuse with a typed error naming the physical reason; a solver-failure refusal is not acceptable;
     - a column with one pumparound, two steam strippers and one reboiled stripper converges;
     - every test under 60 s, with wall times stated.
4. **S0-1c-4 Condenser free-water decant.**
   - At the condenser, the aqueous liquid phase leaves as the internal product `water_decant`; reflux and distillate carry only the hydrocarbon liquid. This is done inside the condenser stage balance, not as a post-solve split.
   - Acceptance:
     - a water-free feed gives a zero decant and an unchanged column (1e-10);
     - a steam-stripped case with decant closes at 1e-8;
     - with decant off and free water at the condenser, the column refuses with a typed error.

Then S0-1 part 2b (the new specs, feature 4) and part 2c (`solve_column_full`, the catalogue R2 flip and adapter, the V1 record). Then S0-3.

## Rules
- Never widen a tolerance, raise a timeout, or change an assertion to match the code's own output. A requirement that cannot be met goes into `assessed` as a measured miss.
- Every typed refusal is reached by a test that converges up to it, with `pytest.raises(OneError, match=...)`.
- Run every local command under `timeout 900`; no full suite or full flowsheet locally. Every loop has an iteration cap that raises a typed error.
- Test cases must be physically sensible: steam stripping at low pressure with heavy cuts, never steam into a 15-bar light-ends column.
