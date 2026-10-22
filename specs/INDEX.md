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
| P1-06 | Staged amine absorber/regenerator via column + amine package | P1-11, P1-09, P1-10, P1-03, P1-04 | BLOCKED again 2026-10-21 (issue #98): amine RR ZeroDivisionError (hotfixed) + reactive mesh floor 1.8e-3 vs locked 1e-6 → P1-11; re-dispatch after P1-11 |
| P1-11 | Reactive-package mesh closure: smooth amine K-values, converged stages, regenerator band | P1-09, P1-10, amine RR hotfix (#151 merged) | steps 1-2 merged #155; steps 3-4 merged #163 (2026-10-22: equilibrium-consistent exact gate for every package, column bench 4959→6508, two-tear polish, NS step controller; MDEA absorber still strict-xfail at M=1.13e-2); step 1 of the follow-up merged #165 (2026-10-22: one stage-K evaluation `_stage_k_values`); next: one shared residual function for gate + NS, exact-residual Jacobian, regenerator (issue #153) |
| P1-12 | Spec secant: warm-chained tear continuation, basin guard (rectifier RR = 0.25 in a cold-solve basin gap) | P1-11 steps 3-5 | issue #157 filed 2026-10-21; spec to write after P1-11 merges |
| P1-10 | One-tear stripper convergence: physical branch selection, band-floor guard | P1-09, #124 | merged #149 (2026-10-21): NS-first for non-reactive one-tear kettles, damped spec secant, band-limit rejection; boundary component balances 1e-6 (NS FD floor) |
| P1-09 | Column zero/one-tear configurations (absorbers, strippers), seed, error containment; amine states inside the column | P1-03, P1-04, P1-08 | merged #125 (2026-10-21): absorbers, Kremser-proper, MDEA column; stripper branch → P1-10 |
| P1-05 | Validation harness: every package vs CoolProp/NIST reference set | P1-01 | merged #97 (867 comparisons, 74 xfail families; issues #99, #100) |
| P1-07 | Pseudo-component definitions owned by the Flowsheet (no process-global registry) | P1-02 | merged #115 (2026-10-21) |
| P1-08 | One saturation solver over a vapour-fraction callable (amine package reuses `_state._saturation`) | P1-01, P1-04 | merged #106 |

Dispatch order: P1-01 first (merged 2026-10-20); then P1-02, P1-03, P1-04, P1-05 in parallel
(disjoint packages; P1-02 and P1-04 both touch `units/`, resolve on rebase); P1-06 after P1-03 and
P1-04 merge. Contract-change PRs are reviewed by the orchestrator before merge.

## Hackathon showcase — the agent (docs/PLAN.md §4)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| B-08 | Engineering agent: Claude tool use over the project, streamed through /api/agent | B-02..B-04, P0-03 | merged #107 |
| F-08 | Agent chat panel streaming /api/agent events | B-08 event schema | merged #104 |

## Phase 2 — Solver and diagnostics (docs/PLAN.md §3)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| P2-02 | Partial results, per-unit error records, convergence history | P1-02, P1-03 | merged #111 (2026-10-21) |
| P2-01 | Flowsheet design specs (Spec/Adjust) with an outer loop; `ngdesign.variables` | P2-02, B-08 | merged #116 (2026-10-21) |
| P2-03 | Per-block tear initialisation; Broyden option for tears | P2-02 | merged #123 (2026-10-21) |
| P2-04 | Case-study runner (CLI, API, agent) | P2-01, B-08 | merged #122 (2026-10-21) |

Dispatch order: P2-02 first (solver + contract), then P2-01 and P2-03 in parallel (P2-01 adds a new
solver module and `variables.py`; P2-03 edits the SM loop), P2-04 after P2-01 and B-08.

## Phase 3 — Platform (docs/PLAN.md §3; parallel with Phase 2)

| Spec | Title | Depends on | Status |
|---|---|---|---|
| P3-01 | Project store (SQLModel), multi-project API, token auth, locked CORS | B-08, P2-02 | merged #109 |
| P3-02 | Solve jobs: queue, worker process, progress stream | P3-01, P2-02 | merged #117 (2026-10-21) |
| P3-03 | Containers, compose, Helm chart, image build on tag | P3-01, P3-02 | merged #121 (2026-10-21) |

Dispatch order: P3-01 after B-08 and P2-02 merge; P3-02 after P3-01; P3-03 after P3-02.

## Unit-operation catalogue (plan: docs/unit-catalogue-plan.md) — starts after the thermo catalogue freeze and P1-11/P1-06; U-00 first, then rounds R0 → R1 → R2 → R3 per family

## Thermo catalogue (plan: docs/thermo-catalogue-plan.md) — starts after P1-09 and P1-06 merge

| Spec | Title | Depends on | Status |
|---|---|---|---|
| T-01 | Thermo catalogue as data: registry, status, L0/L4 validation layers | P1-05, P1-07, #124 | merged #134 (2026-10-21) |
| T-02 | Cubic family options: alpha functions, volume translation, Boston–Mathias, sour terms, all thermo cubic classes | T-01 | merged #161 (2026-10-22): 25 cubic rows (option objects: alpha, translation, liquid density, sour, mixing, LK enthalpy; twu-sim-tassone experimental), per-row `assessed:` declarations, LK D-term fix (#162 closed); catalogue 120 rows |
| T-03 | Gamma-phi adapter: NRTL/UNIQUAC/Wilson/van Laar/Margules/UNIFAC×5 × ideal/virial/cubic vapour; ChemSep + UNIFAC group data | T-01 | merged #150 (2026-10-21): 12 liquids x 5 vapours, 60 rows (virial vapours experimental), in-house van Laar/Margules, 16 live T-12 combos; review fixed Wilson aij, dropped circular fits, L4 refusals once per row |
| T-04 | Helmholtz adapter: IAPWS-95/IF97, CoolProp fluids, GERG-2008 (optional dependency) | T-01 | merged #152 (2026-10-21): iapws95/iapws_if97/coolprop_heos/gerg2008 (CoolProp multifluid path until T-07)/bwrs provisional, 5 placeholders experimental; review added the spec's unit tests, #154 filed |
| T-05 | Classic K-value correlations: Chao–Seader, Grayson–Streed, Braun K10, Lee–Kesler–Plöcker, ideal/Henry | T-01 | merged #158 (2026-10-21): 10 K-value rows provisional (Chao-Seader, Grayson-Streed ×2, Braun K10, LKP, Esso, Antoine/ideal ×3, Henry-Sander), 76/76 comparisons; catalogue 93 rows |
| T-06 | Predictive mixing rules: PSRK, VTPR, MHV1/2, Wong–Sandler, Huron–Vidal, LCVM | T-02, T-03 | planned (issue #141; after T-02+T-03) |
| T-07 | teqp bridge: PC-SAFT, SAFT-VR Mie, CPA, multi-fluid Helmholtz | T-01 | merged #156 (2026-10-21): teqp bridge, 8 saft rows all experimental (CI lacks the extra), hand-rolled CPA-SRK; review: refuse at first use, fixed tolerances with assessed misses |
| T-08 | Model advisor + agent tool `recommend_thermo` + UI package picker | T-01..T-05 | planned (issue #142; after T-01..T-05) |
| T-09 | General electrolytes: eNRTL, Pitzer, extended UNIQUAC, sour water | T-03 | planned (issue #143; after T-03 and #125) |
| T-10 | Solids, polymers, HOC dimerisation, HF | T-03, T-07 | merged #159 (2026-10-21): 5 of 7 family-H rows experimental (flory_huggins, polymer_nrtl, unifac_fv, ideal_solid, hoc_dimer), PhaseKind.SOLID contract change; PolymerPCSAFT + HFHexamer → #160; catalogue 98 rows |
| T-03b | Virial vapour models (Hayden-O'Connell, Nothnagel; Tsonopoulos fallback) for the 24 experimental gamma-phi rows | T-03, T-02 | dispatched 2026-10-22 (issue #166) |
| T-15 | Promotion sweep: validation debt (#100, #130, fitted-to-case rows, CI saft extra, L1 binding), status audit, freeze | T-06, T-08, T-09, T-03b, #160, #164 | spec written 2026-10-22 (issue #167); dispatch after wave 2 merges |
| T-11..T-14 | Validation data sweeps per family (cubic, gamma-phi, Helmholtz/K-value, electrolytes): literature cases with citations, data-only PRs | T-01 | all merged: T-11 #131, T-12 #132, T-13 #135, T-14 #147 (2026-10-21) |

Dispatch: T-01 alone; then T-02, T-03, T-04, T-05, T-07, T-11, T-12, T-13 in parallel (disjoint files); then T-06, T-08, T-09, T-14; then T-10; then the catalogue freeze (status audit).
