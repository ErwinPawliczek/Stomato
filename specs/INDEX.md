# Backlog

| Spec | Title | Wave | Depends on |
|---|---|---|---|
| S-01 | Peng-Robinson thermo package | 0 | none |
| S-02 | B31.3 pipe wall thickness and schedule selection | 0 | none |
| S-03 | Souders-Brown gas capacity | 0 | none |
| S-04 | Counter-current LMTD | 0 | none |
| S-05 | Kremser absorber stage count | 0 | none |
| S-06 | Darcy-Weisbach line pressure drop | 0 | none |
| S-07 | API RP 14E erosional velocity | 0 | none |
| S-08 | Pump hydraulic and shaft power | 0 | none |
| S-09 | API 520 gas relief area (critical flow) | 0 | none |
| S-10 | Control valve Cv (liquid, non-choked) | 0 | none |
| S-11 | B16.5 flange pressure-temperature rating | 0 | none |
| S-12 | P&ID rule: isolation valve at every process nozzle | 0 | none |
| S-13 | P&ID rule: check valve on pump and compressor discharge | 0 | none |
| S-14 | P&ID rule: PSV on every pressure vessel | 0 | none |
| S-15 | P&ID rule: vessel instrumentation | 0 | none |
| S-16 | P&ID rule: pump instrumentation | 0 | none |
| S-17 | P&ID rule: drains at low points, vents at high points | 0 | none |
| S-18 | P&ID SVG renderer | 0 | none |
| S-19 | Isometric SVG renderer | 0 | none |
| S-20 | Line sizing by service velocity limits | 0 | none |
| S-21 | Orthogonal pipe router | 0 | none |
| S-22 | PFD SVG renderer | 0 | none (reuses S-18 symbols if merged, else draws its own) |
| S-23 | Isometric DXF export | 1 | S-19 |
| S-24 | Unit: three-phase separator | 1 | S-01 |
| S-25 | Unit: compressor (isentropic efficiency) | 1 | S-01 |
| S-26 | Units: heater, cooler, air cooler, shell-and-tube (spec outlet T) | 1 | S-01 |
| S-27 | Unit: centrifugal pump | 1 | S-01 |
| S-28 | Units: JT valve, mixer, splitter | 1 | S-01 |
| S-29 | Unit: TEG contactor (spec-based) | 1 | S-01, S-05 |
| S-30 | Sequential-modular flowsheet solver | 1 | S-01 |
| S-31 | Sizer: separators and vessels | 2 | S-03, S-30 |
| S-32 | Sizers: pump, compressor, exchangers | 2 | S-04, S-08, S-30 |
| S-33 | P&ID builder from solved flowsheet | 2 | S-20, S-30, S-31, S-32 |
| S-34 | Relief load and PSV sizing on the P&ID | 2 | S-09, S-14, S-33 |
| S-35 | Slice end to end + CLI | 3 | all slice specs |
| S-40 | Native Peng-Robinson cross-check | stretch | S-01 |
| S-41 | Phase envelope plot | stretch | S-01 |
| S-42 | Absorber stage-stepping diagram | stretch | S-05 |
| S-43 | Deethanizer shortcut (Fenske-Underwood-Gilliland) | stretch | S-01 |
| S-44 | Ergun pressure drop (mol sieve beds) | stretch | none |

Dispatch order: all wave 0 at 11:00 (S-01 first), wave 1 as soon as S-01 merges, wave 2 after the solver, S-35 last. Stretch specs fill any idle agents.

## Layers (frontend + backend move together)

| Layer | Backend | Frontend | Done when |
|---|---|---|---|
| L1 | Project API (done) | F-01 | edit, save, reload round-trips |
| L2 | S-01, S-24..S-30, B-02 | F-02 | slice solves in the UI |
| L3 | S-22, B-03 | F-03 | dragged PFD unit stays put |
| L4 | S-12..S-18, S-33, B-04 | F-04 | every tag in both PFD and P&ID |
| L5 | S-21, B-05 | F-05 | moving equipment re-routes |
| L6 | S-19, B-06 | F-06 | iso BOM/lengths match |
| L7 | B-07 | F-07 | sheet formulas match API |
| L8 | B-08 | F-08 | scripted agent session |

Rule: do not start L(n+1) UI before L(n) passes end to end.

All frontend work follows the UI theme in `specs/frontend/F-09-octagon-ui-theme.md` (reference designs in `specs/frontend/design/`).

## Phase 0 — freeze, measure, de-duplicate (docs/PLAN.md §3)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| P0-01 | Units own their example feeds (break units → flowsheets) | none | merged #82 |
| P0-02 | Amine package owns its equilibrium code (break amine → units) | none | merged #83 |
| P0-03 | One deliverables pipeline module (nothing imports cli) | none | merged #84 |
| P0-04 | One cubic-EOS base; PR/SRK/PR78 become registrations | none | merged #86 |
| P0-05 | Engineering layer de-duplication | none | merged #87 |
| P0-06 | Benchmark baseline (flash count + wall time) in CI | none | merged #85 |

Phase 0 complete 2026-10-20 (six specs, six parallel agents, zero numeric drift). All six were independent; each deleted
its own `.importlinter` ignore lines. The orchestrator updates **Status** here on merge.

## Phase 1 — contracts v2: the fundamental fix (docs/PLAN.md §3)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| P1-01 | Thermo contract v2 — properties, K-values, saturation, derivatives | P0-04, P0-06 | merged #89 |
| P1-02 | Open component registry — databank species, pseudo-components, per-flowsheet slate | P0-01, P1-01 | merged #94 |
| P1-03 | Column consumes contract v2; split the god-file | P1-01, P0-06 | merged #96 (−56 % flash-equivalents; see #91) |
| P1-04 | Amine chemistry as property packages (apparent-component reactive VLE) | P0-02, P1-01 | merged #95 |
| P1-06 | Staged amine absorber/regenerator via column + amine package | P1-03, P1-04 | dispatched (issue #98) |
| P1-05 | Validation harness: every package vs CoolProp/NIST reference set | P1-01 | merged #97 (867 comparisons, 74 xfail families; issues #99, #100) |
| P1-07 | Pseudo-component definitions owned by the Flowsheet (no process-global registry) | P1-02 | drafted |
| P1-08 | One saturation solver over a vapour-fraction callable (amine package reuses `_state._saturation`) | P1-01, P1-04 | merged #106 |

Dispatch order: P1-01 first (merged 2026-10-20); then P1-02, P1-03, P1-04, P1-05 in parallel
(disjoint packages; P1-02 and P1-04 both touch `units/`, resolve on rebase); P1-06 after P1-03 and
P1-04 merge. Contract-change PRs are reviewed by the orchestrator before merge.

## Hackathon showcase — the agent (docs/PLAN.md §4)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| B-08 | Engineering agent: Claude tool use over the project, streamed through /api/agent | B-02..B-04, P0-03 | dispatched (issue #101) |
| F-08 | Agent chat panel streaming /api/agent events | B-08 event schema | merged #104 |

## Phase 2 — Solver and diagnostics (docs/PLAN.md §3)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| P2-02 | Partial results, per-unit error records, convergence history | P1-02, P1-03 | dispatched (issue #103) |
| P2-01 | Flowsheet design specs (Spec/Adjust) with an outer loop; `ngdesign.variables` | P2-02, B-08 | drafted |
| P2-03 | Per-block tear initialisation; Broyden option for tears | P2-02 | drafted |
| P2-04 | Case-study runner (CLI, API, agent) | P2-01, B-08 | drafted |

Dispatch order: P2-02 first (solver + contract), then P2-01 and P2-03 in parallel (P2-01 adds a new
solver module and `variables.py`; P2-03 edits the SM loop), P2-04 after P2-01 and B-08.
