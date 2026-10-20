# Stomato: state of the codebase and the end-goal plan

Written 2026-10-20 from a full read of `main` (83 commits, 780 tests green, 16k lines Python).

## 1. Where we are

**What exists and works.** A natural-gas design engine: PR/SRK/PR78/NRTL thermo delegated to
Caleb Bell's `thermo`, 20 unit ops incl. a rigorous inside-out column (`units/column.py`), a
sequential-modular solver with SCC tearing and bounded Wegstein, sizers, a P&ID rule engine that
runs to a fixed point, an orthogonal router, SVG PFD/P&ID/iso renderers, a FastAPI wrapper and a
React UI. `python -m ngdesign.cli slice` produces every deliverable from one flowsheet. CI is
strict (mypy strict, ruff, OpenAPI drift check both sides, locked-path guard).

**What is genuinely good and must be kept**
- Pydantic contracts that validate and serialise to JSON (`contracts/`).
- The decorator registry plus the shared property tests (every unit closes balances on its own
  `example_case`, every P&ID rule is idempotent and composes).
- Solver structure: deterministic SCC decomposition, tearing, honest `converged` flag.
- Column algorithm (Boston–Sullivan inside-out, Naphtali–Sandholm fallback, exact energy closure).
- Golden-data oracles (`data/golden/*.yaml`) and the standards-cited docstrings.
- The deliverables chain (`sizing`, `pid_rules`, `piping`, `render`) imports **no** thermo code
  and consumes only `SolvedFlowsheet`/`PID`. This is already a clean service seam.

**The ten structural problems, by severity**

| # | Problem | Where |
|---|---|---|
| 1 | Thermo contract is three flashes (PT/PH/PS). No fugacity, K-values, phase enthalpy, bubble/dew, TVF, derivatives. The column rebuilds all of these from 10^4–10^5 extra PT flashes. | `contracts/plugins.py:19-24`, `units/column.py:392-568` |
| 2 | Component set is a closed 18-tuple and the solver tear vector is indexed by it. Natural-gas only by construction; `components.yaml` Tc/Pc/ω are dead data (EOS pulls from `chemicals` by CAS). | `contracts/stream.py:9-28`, `solver/sequential_modular.py:69-70` |
| 3 | No flowsheet-level design spec / Adjust / Set; no equation-oriented path; any unit exception aborts the whole solve with no partial result. | `solver/sequential_modular.py:33-35,386` |
| 4 | API state is process globals: one project, unbounded solve cache, module-level iso placements. Sync handlers, no job model, no auth, CORS `*`. Cannot run two replicas. | `api/app.py:36`, `api/routes_solve.py:23`, `api/routes_iso.py:34` |
| 5 | Pipeline orchestration lives in private `cli.py` helpers that the API and `export.py` import; the routed-network chain is copy-pasted between two route files. | `cli.py`, `api/routes_plot.py:50`, `api/routes_iso.py:37` |
| 6 | Dependency inversions: 7 units import `flowsheets.slice`; `amine/` imports private names from `units/`; `teg_contactor` imports `sizing`; `mixer` imports `jt_valve`. | `units/*.py`, `amine/enrtl.py:161` |
| 7 | `pr.py`/`srk.py`/`pr78.py` are ~95 % identical; `nrtl.py` ~75 %. ~1060 lines that should be ~350. | `thermo/` |
| 8 | "One spec = new files only" produced patch-stacking: `npsh_available` and `lmtd_counter` re-implemented in `machines.py`, `_sizer_for`/`_layout`/`_topological_layers`/`_psv_nozzle` duplicated across 2–3 files, iso placements routed around the locked `Layout` contract. | `sizing/machines.py:134-160`, `pid_rules/builder.py:130` vs `cli.py:48` |
| 9 | Amine/TEG units are spec-driven, non-staged, and their outlet enthalpies come from a cubic EOS that ignores the chemistry. Energy numbers are not trustworthy. Slice constants leak into general code (`k_gas=1.24`, `_DEFAULT_BASIS` from V-101). | `units/mdea_*`, `pid_rules/psv_sizing.py:126`, `cli.py:35` |
| 10 | The product surface is thin: no LLM agent (`AgentView` is a hard-coded transcript, B-08 unbuilt), no graphical flowsheet canvas, sheet view has no formulas, iso tab is a placeholder, every spec checkbox is still `[ ]`, 48 stale branches. | `frontend/src/views/AgentView.tsx:6`, `specs/` |

## 2. The decision on Kubernetes

Kubernetes is a fine **deployment** target. It is the wrong **modularity** tool for this codebase.
The modularity you want is *library* modularity with enforced import boundaries; the deployable
units fall out of that, and there are only three of them.

Why not microservice the engine: a column solve makes on the order of 10^4–10^5 flash calls.
At today's ~20 ms per flash an RPC hop adds maybe 5–10 %; the moment the flash is made fast
(which is Phase 1), the network would dominate by >20×. Unit ops inside a recycle cannot run in
parallel anyway, so per-unit services buy nothing. Thermo + units + solver stay in one process.

**Target shape**

```
packages/                      (one uv workspace, one repo, enforced with import-linter)
  stomato-core        contracts, registry, component database, unit-of-measure layer
  stomato-thermo      property packages (one cubic-EOS base; PR/SRK/PR78 are parameter sets),
                      NRTL, e-NRTL, flash algorithms, property cache
  stomato-units       unit operations (depends on core + thermo only)
  stomato-solver      sequential-modular + specs/adjust; EO later
  stomato-engineering sizing, P&ID rules, routing, renderers, export (depends on core only)
  stomato-api         HTTP, project store, job queue, auth
  stomato-agent       Claude tool-use agent over the API
frontend/

deploy/ (Helm chart)
  api            stateless, N replicas
  solve-worker   consumes jobs; one solve = one job; scales for case studies
  deliverables   stateless; SolvedFlowsheet JSON in → SVG/DXF/CSV out
  web            static
  postgres       projects, users, results
  redis          queue + solve cache
```

Allowed import direction: `engineering → core`, `units → thermo → core`, `solver → units`,
`api → solver, engineering`, `agent → api client`. Nothing imports `flowsheets/` or `cli.py`.
CI fails on any other edge (`import-linter` contract file checked in).

## 3. Phases

Each phase ends with a measurable gate. Phases are sequential at the contract level, but the
executables inside a phase are independent and can be dispatched in parallel to Obvious.

### Phase 0 — Freeze, measure, de-duplicate (1 week)
Gate: same 780 tests green, benchmark harness checked in, import-linter green, zero duplicated
engineering functions.
- Delete the 48 stale remote branches (all squash-merged leftovers; keep `fix/column-timing-flake`).
- Add `import-linter` with the dependency contract above; fix the inversions in problem 6.
- Collapse `pr/srk/pr78` into one `CubicEOS` base with three registrations; share helpers with NRTL.
- Remove duplicated correlations in `machines.py`; wire to the registered plugins. Single
  `_sizer_for`, `_layout`, `_topological_layers`, `_psv_nozzle`.
- Lift the pipeline out of `cli.py` into `engineering/pipeline.py`; CLI, API and export call it.
- Benchmark harness (`scripts/bench_harness.py` exists; extend): flash count, wall time, and
  convergence per flowsheet; results committed as JSON so regressions are visible in PRs.
- Replace the "new files only" rule with package ownership + the import contract (see §5).

### Phase 1 — Contracts v2: the fundamental fix (2–3 weeks)
Gate: column solves with ≤10 % of today's flash count; any `chemicals`-databank species can be
added to a flowsheet; cross-check against DWSIM and CoolProp on a reference case set.
- **Thermo contract**: `fugacity_coefficients`, `k_values`, `phase_enthalpy`, `phase_entropy`,
  `bubble_T/P`, `dew_T/P`, `flash_tvf`, `cp`, `dH/dT`, `dlnK/dT`; a property cache keyed on
  rounded state; all returned as typed records, not dicts.
- **Open component set**: `Component` record (CAS, formula, MW, Tc, Pc, ω, ideal-gas Cp
  coefficients, provenance) loaded from a database layer over `chemicals`, with user-defined
  pseudo-components (C6+ by Tb/SG via Twu/Lee–Kesler) and a per-project component list. The
  18-tuple becomes a default slate, not a type.
- `StreamState` v2: per-phase H, S, Cp, fugacities; `mass_flow` never raises.
- Migrate the column to consume `k_values`/`phase_enthalpy` directly; split `column.py` into
  `column/{spec,initialise,inside_out,naphtali_sandholm,linalg}.py`.
- Lift Kent–Eisenberg / e-NRTL to real thermo packages so amine outlet enthalpies include
  chemistry; staged absorber/regenerator become `column` with a reactive package.

### Phase 2 — Solver and diagnostics (2 weeks)
Gate: a design spec (e.g. "set K-101 discharge P so T-101 water dewpoint = X") converges on the
slice; a failed unit yields a partial `SolvedFlowsheet` with a per-unit error record.
- Flowsheet-level `Spec`/`Adjust`/`Set` objects in the contract; outer Broyden around SM.
- Smarter tear initialisation (per-SCC feed, not global mean); Broyden option for tears.
- Partial results and convergence history in `SolvedFlowsheet` so the UI can show them.
- Case-study runner: parameter grid → N jobs → table.

### Phase 3 — Platform (2 weeks, parallel with Phase 2)
Gate: two API replicas behind one URL, projects survive restart, a 10-minute solve shows progress.
- Project store (Postgres via SQLModel), multi-project, user accounts, token auth, CORS locked.
- Job model: `POST /jobs/solve` → id; worker pulls from Redis; `GET /jobs/{id}` streams progress.
- Deliverables service as its own container taking `SolvedFlowsheet` JSON.
- Helm chart + `docker compose` for local; GitHub Actions builds images on tag.

### Phase 4 — Product (3 weeks)
Gate: a process engineer builds a 6-unit flowsheet from a blank canvas, solves, reads results and
exports PFD/P&ID/iso without touching JSON.
- Graphical flowsheet canvas (ports, drag-to-connect, inline unit spec panel).
- Real agent (B-08): Claude tool-use over the API — `add_unit`, `connect`, `set_spec`, `solve`,
  `case_study`, `render`; streaming transcript in `AgentView`.
- Iso tab wired to B-06; export buttons (SVG/DXF/CSV/PDF); sheet view with formulas (B-07).
- Convergence diagnostics panel; unit-level error display.

### Phase 5 — Breadth (ongoing)
Rigorous heat-exchanger rating (`ht`), CSTR/PFR with kinetics, PC-SAFT/CPA via `thermo`,
electrolytes beyond amines, dynamic mode (later), DWSIM/Aspen file import.

## 4. Hackathon showcase (what to build first for the $20k of tokens)

The highest-leverage demo is the agent: a chat where you say *"50 MMSCFD wet sour gas at 500 psia,
sweeten with MDEA, dehydrate with TEG, compress to 1200 psia"* and the system builds, solves,
and hands back PFD + P&ID + isos. Everything that demo needs except the agent already exists.
Order: Phase 0 (so the agent is built on clean seams) → B-08 agent → Phase 1 in the background.

## 5. How we run the agents from here

- **Claude Code (this session) is the architect/orchestrator**: writes specs with acceptance
  tests, dispatches, reviews every PR via `gh`, merges, keeps this document current.
- **Obvious Autobuild is the implementer fleet**: one executable = one spec. Dispatched either
  as workspace initiatives or via `POST /api/v1/projects/{id}/thread` with the spec as
  `starterPrompt`; results come back as GitHub PRs, which is the only channel we need.
- **Governance change**: drop "new files only". Replace with
  (a) package ownership — a spec names the package it may edit;
  (b) `import-linter` contract — CI enforces the dependency direction;
  (c) keep the oracle lock (`tests/golden`, `tests/property`, `data/golden`) — those stay human-only;
  (d) contracts become editable **by spec**, with a `contract-change` label and the orchestrator
  as reviewer, instead of being frozen. A frozen contract is why problems 1, 2 and 8 exist.
- Spec template gains: *package(s) touched*, *benchmark delta expected*, *oracle added*.

## 6. Is "Aspen Plus, but modular" doable?

Honestly: the **engine** is doable; the **data** is the moat, and Aspen's 40-year lead is mostly
in regressed parameters, not code. DWSIM (one author, ~15 years, C#) proves a single developer
can reach "usable rigorous simulator". With agents and $20k of tokens, the code is not the
bottleneck. What decides credibility:

| Aspen Plus has | Open equivalent we can stand on | Gap |
|---|---|---|
| Pure-component DB (~8 k species, DIPPR-regressed) | `chemicals` databank (~20 k species: Tc/Pc/ω/Cp/Psat/ΔHf…), NIST WebBook, CoolProp (120 fluids, reference EOS) | provenance/quality grading per property |
| Binary interaction parameters (NRTL/UNIQUAC/PR k_ij) | ChemSep IPDB (already used), published UNIFAC/mod-UNIFAC groups, PR k_ij from literature | regression tool for user data |
| Property methods (PR, SRK, PC-SAFT, NRTL, ELECNRTL, steam tables…) | `thermo` lib already implements cubics, PC-SAFT, NRTL/UNIQUAC/UNIFAC, IAPWS-95; we have e-NRTL | one uniform contract over them |
| Flash (PT, PH, PS, TVF, PVF, 3-phase, stability) | `thermo.FlashVLN` | TVF/PVF, derivatives, speed |
| Unit ops (~60) | we have 20; `ht`/`fluids` give rating correlations | reactors, rigorous HX, more columns |
| RadFrac | our inside-out column | reactive/3-phase stages, pumparounds, side strippers |
| SM + EO solvers, design specs, sensitivity, optimisation | our SM; `scipy` for EO Newton/IPOPT-via-cyipopt | EO path, specs, sensitivity |
| Aspen Properties / regression | — | later, the DRS equivalent |
| Dynamics, Energy Analyzer, EDR, Economics | — | out of scope for v1 |

Verdict: build a **general-purpose steady-state simulator** with Aspen's *structure* (property
method → flash → unit ops → flowsheet solver → analysis tools) and *open, graded* data. That is
a 6–9 month build with a fleet of agents, not a 10-year one. "All of Aspen" is not the goal.

## 7. Engine outline: exactly what the simulation engine needs

Package by package, in dependency order. ✅ exists, 🟡 exists but must change, ❌ missing.

**stomato-core**
- ❌ Unit-of-measure layer (SI internally, typed quantities at the edges; display sets).
- 🟡 `Component` record + **open component registry** (CAS-keyed, provenance per property,
  pseudo-components by Tb/SG, user components). Replaces the 18-tuple.
- 🟡 `StreamState` v2: T, P, flow, overall z, per-phase {β, x, H, S, Cp, ρ, μ, k, σ, φ}.
- 🟡 `Flowsheet` v2: units, streams, **design specs / adjust / set**, case-study definitions.
- ✅ Registry, plugin kinds, `SolvedFlowsheet`, `Datasheet`, `PID`, `PipingNetwork`.
- ❌ Result/diagnostic records: per-unit status, convergence history, warnings with provenance.

**stomato-thermo**
- 🟡 **Property-package contract v2**: `flash_pt/ph/ps/tvf/pvf`, `bubble/dew T,P`, `fugacity`,
  `k_values`, phase `H/S/Cp/G`, `dlnφ/dT, dlnφ/dP, dlnφ/dn`, transport (ρ, μ, k, σ), stability.
- 🟡 One `CubicEOS` base (PR, SRK, PR78, PRSV, with α-function and mixing-rule plugins);
  `k_ij` from a graded BIP store.
- 🟡 Activity packages: NRTL ✅, UNIQUAC, UNIFAC/mod-UNIFAC (predictive — critical for species with
  no BIPs), Wilson; γ-φ framework shared.
- 🟡 Electrolyte: e-NRTL promoted to a package; Kent–Eisenberg as the cheap fallback.
- ❌ PC-SAFT and CPA (via `thermo`), IAPWS-95 steam, ideal.
- ❌ Property cache (rounded-state key, LRU) and a flash benchmark suite (ms/flash tracked in CI).
- ❌ Validation harness: every package vs CoolProp/NIST on a reference case set, tolerance per
  property, results committed.

**stomato-units** (all consume the contract only; none import thermo packages or flowsheets)
- ✅ mixer, splitter, heater/cooler, air cooler, shell-and-tube (spec), JT valve, pump,
  compressor, expander, compression train, 2/3-phase separators, scrubber.
- 🟡 Column: split god-file; stage model with reactive/3-phase/side-draw/pumparound; shortcut
  (FUG) as a separate unit; absorber/stripper as column configurations.
- 🟡 Amine/TEG: become column + electrolyte package; keep spec-based as "shortcut" variants.
- ❌ Heat exchanger **rating** (LMTD-F, ε-NTU, multi-stream/LNG), fired heater.
- ❌ Reactors: conversion, equilibrium (Gibbs min), yield, CSTR, PFR (kinetics), with reaction set
  contracts.
- ❌ Flash drum with heat duty, tank, pipe segment (Beggs–Brill/`fluids`), valve (Cv-based),
  relief valve, orifice, hydrate inhibitor injection.
- ❌ Logical: recycle block (explicit tear with options), set, adjust, balance, stream calculator.

**stomato-solver**
- ✅ Sequential-modular: SCC decomposition, tearing, bounded Wegstein.
- ❌ Tear options: direct substitution / Wegstein / Broyden / Newton; per-SCC initial guesses.
- ❌ Design specs & adjust via outer Broyden; nested convergence blocks.
- ❌ Partial results; per-unit failure records; convergence history.
- ❌ Case study / sensitivity runner (grid → jobs → table); optimisation hook (scipy / IPOPT).
- ❌ Equation-oriented path (Phase 5+): unit ops expose residuals + Jacobian; sparse Newton.

**stomato-engineering** (deliverables; consumes `SolvedFlowsheet` only)
- ✅ sizers, P&ID builder, 7 rules, orthogonal router, SVG PFD/P&ID/iso, CSV/HTML export.
- 🟡 Pipeline module (lift out of `cli.py`); relief basis from the real case.
- ❌ DXF export (ezdxf is already a dep), PDF, datasheet PDFs, equipment list, line list.

**stomato-api**: project store (Postgres), users/auth, job queue + solve worker, SSE progress,
versioned project history, import (DWSIM .dwxmz / Aspen .bkp parsing as a stretch).

**stomato-agent**: Claude tool-use over the API (build, spec, solve, case-study, explain
results, render); eval suite of scripted sessions.

**frontend**: graphical flowsheet canvas, unit spec panels, results grid with formulas, drawings
with placement, convergence panel, agent chat, project browser.

## 8. Operating model with Obvious

Confirmed by smoke test 2026-10-20: `POST /projects/prj_yONapyzq/thread` starts an autonomous
agent in the "simulation engine cleanup" project; there is no read-back API.
Loop: spec in repo → thread with `starterPrompt` = spec path + rules → `successPrompt` = "open PR,
then comment the PR URL on GitHub issue #N" / `failurePrompt` = "comment the blocker on issue #N"
→ orchestrator watches the issue + PRs with `gh`, reviews, merges. GitHub is the ledger.
