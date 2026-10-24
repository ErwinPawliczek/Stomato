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
| P1-11 | Reactive-package mesh closure: smooth amine K-values, converged stages, regenerator band | P1-09, P1-10, amine RR hotfix (#151 merged) | steps 1-2 merged #155; steps 3-4 merged #163 (2026-10-22: equilibrium-consistent exact gate for every package, column bench 4959→6508, two-tear polish, NS step controller; MDEA absorber still strict-xfail at M=1.13e-2); step 1 of the follow-up merged #165 (2026-10-22: one stage-K evaluation `_stage_k_values`); step 2 + ruling (c) merged #174 (2026-10-22: one shared live residual `_live_residual_vector` for gate and NS, model-validity LM fallback replaces the step caps, per-row M scales frozen once per NS pass on the 0/1-tear path; two-tear warm path keeps per-evaluation scales — measured deethanizer regression, follow-up; stripper D=11.8267 in band); remaining: reactive absorber stall at M=1.13e-2 (step 3), reactive gate floor, regenerator ZeroDivisionError (issue #153); #202 (836c484) 2026-10-23: absorber closes at 1e-3, liquid-edge continuity, regenerator RR form; R1 merged #204 (5398d10) 2026-10-23: exothermic absorption-heat reference ships, exact-residual seeds + generic heat-scale continuation (0→1 in 0.25 steps) for cold reactive 0/1-tear solves, max T 304.34 K @ stage 20, temperature-band xfail removed, backend CI 30 min; DONE, issue #153 closed |
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

## Unit-operation catalogue (plan: docs/unit-catalogue-plan.md, approved 2026-10-23) — basic R0 for all 83 units first, then crude refining (S0) rigorous, then S1/S3/S2

| Spec | Title | Depends on | Status |
|---|---|---|---|
| U-R | Reaction-set contract: stoichiometry, kinetics forms, formation properties, extent arithmetic | none | merged #199 (676aac1) 2026-10-23; issue #192 |
| U-R1 | Round-1 conventions binding every family thread (R0 adapter, YAML flip, cited V1, closed-form test, ownership) | U-00, U-R, U-01 | in progress: round 1 dispatched 2026-10-23 19:11 CDT (U-A..U-H1; U-H2 after U-F1) |
| U-A | Logical units R0 (+ U-A1 `_physics/splitting.py`; solver lowering for adjust/recycle) | U-R1 | issue #206 |
| U-B | Flow units R0 (+ `_physics/efficiency.py`) | U-R1 | issue #207 |
| U-C | Heat units R0 (+ `_physics/heat_balance.py`: two-stream, multi-stream, problem table) | U-R1 | issue #208 |
| U-D | Separation units R0 | U-R1, U-A1 (3 units) | DONE 2026-10-24 (#224, 501afcc): flash_drum, decanter, tank, adsorption_bed, hydrate_check, hydrocyclone, filter, membrane R0 |
| U-E | Shortcut column units R0 (+ `_physics/shortcut.py`: FUG, Kremser fraction; V2 vs MESH) | U-R1, P1-11 | DONE 2026-10-24 (#225, 1534141): FUG + Kremser absorber, stripper, extractor R0; V2 vs MESH measured |
| U-F | Reactors R0 (+ U-F1 `kinetics.yield_shift`, `_physics/gibbs.py`; solver reaction-set hook) | U-R1 | issue #211 |
| U-G | Treating R0: TEG regenerator, Claus | U-R1 | in progress: #221 merged (3d67eae) teg_regen R0 + unregistered Claus; U-G2 (Claus registration + V1) dispatched 2026-10-24 |
| U-H1 | Refining separation R0: assay feeder, desalter, crude/vacuum cut-point columns, side strip, preflash, blending | U-R1, A-01, U-E (side_strip) | issue #213 |
| U-H2 | Refining reactors R0: lumped yield correlations | U-R1, U-F1 | DONE 2026-10-23 (#218, 0c8f357): naphtha_ht, reformer_cat, coker R0; fcc and hcu refused (figure-only sources), issue #222 pseudo characterisation |
| U-00 | Unit catalogue as data: 83-row YAML registry, rigour-level dispatch/refusal, V0 harness | none | merged #197 (8cf4d20) 2026-10-23; issue #189 |
| U-01 | Unit harness: cited V1 cases with tolerances and assessed misses, mass/element V0 for reactive rows, per-row example thermo | U-00, U-R | DONE 2026-10-23 (#205, 8cc9b2b; U-01b reactive balance bases #220, 16432b9) |
| A-01 | Crude assay characterisation: curve conversions, light ends, pseudo cutting, S0 reference data | P1-07 | merged #195 (2026-10-23): `contracts/assay.py`, `data/assay.py` (`data.py` became the `data/` package); D86→TBP Riazi–Daubert, D2887→TBP API 3A3.1 (Daubert 1994 °F table), D1160 at 10 mmHg via the graphical 3A2.1 procedure (other pressures refuse), Maxwell–Bonnell AET; S0 reference = Bagajewicz & Ji 2001 Part I cut temperatures/gaps only — round 2 needs a yields source (Part II) |

Round 1 (palette R0, one thread per family U-A..U-H) after U-00 and U-R merge; round 2 (S0 crude to R1/R2) after round 1 and P1-11.

## Thermo catalogue (plan: docs/thermo-catalogue-plan.md) — starts after P1-09 and P1-06 merge

| Spec | Title | Depends on | Status |
|---|---|---|---|
| T-01 | Thermo catalogue as data: registry, status, L0/L4 validation layers | P1-05, P1-07, #124 | merged #134 (2026-10-21) |
| T-02 | Cubic family options: alpha functions, volume translation, Boston–Mathias, sour terms, all thermo cubic classes | T-01 | merged #161 (2026-10-22): 25 cubic rows (option objects: alpha, translation, liquid density, sour, mixing, LK enthalpy; twu-sim-tassone experimental), per-row `assessed:` declarations, LK D-term fix (#162 closed); catalogue 120 rows |
| T-03 | Gamma-phi adapter: NRTL/UNIQUAC/Wilson/van Laar/Margules/UNIFAC×5 × ideal/virial/cubic vapour; ChemSep + UNIFAC group data | T-01 | merged #150 (2026-10-21): 12 liquids x 5 vapours, 60 rows (virial vapours experimental), in-house van Laar/Margules, 16 live T-12 combos; review fixed Wilson aij, dropped circular fits, L4 refusals once per row |
| T-04 | Helmholtz adapter: IAPWS-95/IF97, CoolProp fluids, GERG-2008 (optional dependency) | T-01 | merged #152 (2026-10-21): iapws95/iapws_if97/coolprop_heos/gerg2008 (CoolProp multifluid path until T-07)/bwrs provisional, 5 placeholders experimental; review added the spec's unit tests, #154 filed |
| T-05 | Classic K-value correlations: Chao–Seader, Grayson–Streed, Braun K10, Lee–Kesler–Plöcker, ideal/Henry | T-01 | merged #158 (2026-10-21): 10 K-value rows provisional (Chao-Seader, Grayson-Streed ×2, Braun K10, LKP, Esso, Antoine/ideal ×3, Henry-Sander), 76/76 comparisons; catalogue 93 rows |
| T-06 | Predictive mixing rules: PSRK, VTPR, MHV1/2, Wong–Sandler, Huron–Vidal, LCVM | T-02, T-03 | step 1 merged #175 (2026-10-22): `thermo/mixing_rules.py` hosts gE rules as GCEOSMIX a_alpha overrides (ln phi vs FD 1e-8, vdW1 identity), pr_huron_vidal provisional with 6 declared misses (low-pressure NRTL parameters do not transfer to the HV reference; 2 C1/H2O cases unbound: refusal); catalogue 129 rows; remaining 8 rules in flight (issue #141, fourth thread); T-06a merged #181 (2026-10-22): pr_wong_sandler + srk_wong_sandler provisional (WS 1992 Q/D form, C_PR=-0.62323, C_SRK=-ln2; ln phi vs Helmholtz FD 1.1e-8; MeOH/H2O bubble_T +0.8/+1.0 % vs HV +3.5 %; 12 misses assessed each, 4 C1/H2O cases unbound: refusal; follow-up: T-dependent b_m vs T-independent-covolume departure kernel → approximate mixture Cp), catalogue 131 rows; steps 3/4 split into parallel T-06b (MHV1/MHV2) and T-06c (PSRK/VTPR/LCVM), dispatched 2026-10-22; T-06b merged #182 (2026-10-22): pr_mhv1, pr_mhv2, srk_mhv2 provisional (Michelsen 1990 q1 -0.53/-0.593; Dahl & Michelsen 1990 MHV2 PR -0.4347/-0.003654, SRK -0.4783/-0.0047; root choice gives alpha = S on pure feeds; MHV2 T-derivative bugs inherited from the retired thread's stray code fixed + gated by TestMHVTDerivatives; 18 cases bound, C1/H2O unbound: refusal; orchestrator merged main and rebuilt mixing_rules.py/mixing.yaml), catalogue 134 rows; T-06c merged #184 (2026-10-22): psrk (main's MHV1, q1 -0.64663, PSRK-UNIFAC, Mathias-Copeman SRK; C1/H2O cases pass), vtpr (A1 -0.53087 residual gE on Twu-PR; declared linear-b/generalised-Twu deviations), lcvm (Boukouvalas 1994: lambda 0.36 on Vidal, A_V -0.623, A_M -0.52, original UNIFAC; C1/H2O unbound: refusal) provisional; orchestrator review fixed swapped LCVM weights, wrong A_M, reversed covolume sign in LCVM and the duplicate MHV1Rule, wrong LCVM citation (LCVM bubble_T +2.8 → +0.57 %); found HV constant bug → #185; **catalogue 137 rows — T-06 complete**; #185 fixed by #186 (2026-10-22, admin-merged after full green CI): HuronVidal.M_PR was ln(sqrt2-1) = -0.881 (sign and sqrt2 wrong) → 0.62323; pr_huron_vidal MeOH/H2O bubble_T +3.5 → +1.1 %, bubble_P -35.7 → -10.4 %; closed-form constant test added. T-06 closed (#141) |
| T-07 | teqp bridge: PC-SAFT, SAFT-VR Mie, CPA, multi-fluid Helmholtz | T-01 | merged #156 (2026-10-21) + #170 (2026-10-22, #164 closed): teqp bridge, 8 saft rows all experimental (CI lacks the extra), hand-rolled CPA-SRK, gerg2008_teqp exact backend + soft_saft refusal; review: refuse at first use, fixed tolerances with assessed misses; catalogue 124 rows |
| T-08 | Model advisor + agent tool `recommend_thermo` + UI package picker | T-01..T-05 | merged #168 (2026-10-22): thermo/advisor.py (ranked recommendations with cited reasons), agent tool recommend_thermo, GET /api/thermo/recommend + /api/thermo/models (selectable flag, #154 closed) |
| T-09 | General electrolytes: eNRTL, Pitzer, extended UNIQUAC, sour water | T-03 | merged #171 (2026-10-22): pitzer_nacl_water + sour_water provisional (Pitzer-Peiper-Busey 1984 / EPA-600/2-80-067 anchors in tests/thermo/test_electrolyte.py), enrtl_nacl_water + ext_uniquac_nacl_water experimental first-use refusals (published Chen & Evans 1986 / Thomsen & Rasmussen 1999 parameter sets → T-15 follow-up); 4 of the plan's ~6 G rows (physical solvents absent); catalogue 128 rows; T-09b merged #183 (2026-10-22, #173): enrtl_nacl_water (Chen & Evans 1986 tau pair via Kwaterski & Herri, PDH rho 14.9) and ext_uniquac_nacl_water (Thomsen & Rasmussen 1999 set verified against Leal et al. 2025; psi_ji = exp[(u_ii-u_ji)/T]) are real provisional rows replacing the refusals; PPB84 anchors at default tolerances, misses assessed (eNRTL gamma+- worst -4.99 % @ 6 m, eUNIQUAC phi worst +3.68 % @ 4 m); Reaktoro cross-check only |
| T-10 | Solids, polymers, HOC dimerisation, HF | T-03, T-07 | merged #159 + #169 (2026-10-22): all 7 family-H rows (polymer_pc_saft and hf_hexamer experimental, #160 closed); PhaseKind.SOLID; catalogue 122 rows |
| T-03b | Virial vapour models (Hayden-O'Connell, Nothnagel; Tsonopoulos fallback) for the 24 experimental gamma-phi rows | T-03, T-02 | merged #172 (2026-10-22): in-house HOC kernel (`thermo/virial.py`, eta table from ChemSep HAYDENO.IPD), the 12 Nothnagel rows run the declared Tsonopoulos-extended fallback (1973 b/K table not open), all 24 rows provisional with L0 green (nrtl_hoc/wilson_nothnagel carry L1/L2 cases; promotion waits on #100 → T-15 item 8); acids (eta ≥ 4) refuse to hoc_dimer; catalogue 128 rows, 0 experimental virial rows |
| T-15 | Promotion sweep: validation debt (#100, #130, fitted-to-case rows, CI saft extra, L1 binding), status audit, freeze | T-06, T-08, T-09, T-03b, #160, #164 | spec written 2026-10-22 (issue #167); dispatched 2026-10-22 05:50 after T-09/T-03b merged (T-06 still in flight; thread told to avoid its files); CI `--extra saft` merged #178 (teqp 0.23.2 on CI, SAFT tests run, audit PASS) partial merged #176 (2026-10-22): validated 4 → 9 (coolprop_heos, gerg2008, chao-seader, lee-kesler-ploecker, henry-sander), MEG/H2O independent point declared, IF97 saturated-phase label swap filed #177; item 1 merged #179 (2026-10-22: retired Bennett 1929 MeOH/H2O 97.99 kPa series replaced by Gao et al. 2012 at 101.325 kPa; nrtl and wilson_nothnagel 8/8 on it, no promotions; #100 resolved); T-15c merged #180 (2026-10-22): 35 SAFT cases bound, pc_saft (44/62) and cpa_srk (40/62) experimental → provisional with every miss assessed, 3 MeOH/H2O 101.325 kPa cases stay pending:cpa_srk (Wilson-seed SaturationError), multifluid stays experimental (CoolProp fluid library not redistributable); Mørch 2006 confirmed, #130 closed; HOC acetic-acid B(400 K) anchor = recorded gap (no open source), hoc_dimer vs nrtl_hoc 34 % gap pinned and explained in test_virial; review commit: per-(case, package) citation lookup + item-10 status summary in docs/validation.md; catalogue 129 rows = 9 validated / 97 provisional / 23 experimental |
| T-16a | ASME steam (IF97 basis, fixes #177), AGA8 DC92, Twu–Sim–Tassone to real rows | T-04, T-15 | merged #198 (19f2adb) 2026-10-23: AGA8 DC92 (NIST port), ASME/IF97 row, TST; fixes #177; issue #187 |
| T-16b | MBWR, BWR-Lee-Starling, EOS-CG to real rows | T-04, T-07, T-15 | merged #203 (2d6b422) 2026-10-23: mbwr provisional (Younglove-Ely, ethane G(3) corrected, 105/105), bwr_ls provisional (14/17, Cp misses assessed), eos_cg refused (paywalled parameter supplement); issue #194 |
| T-17 | SAFT association and polar: PC-SAFT assoc, polar PC-SAFT, CPA-PR, soft-SAFT | T-07, T-15c | issue #191; dispatched 2026-10-23 |
| T-18 | teqp-backed rows to provisional: SAFT-VR Mie, multifluid, multifluid pure, GERG-2008 teqp | T-07, T-15c, #178 | merged #201 (63e576c) 2026-10-23: saft_vr_mie, multifluid, multifluid_pure, gerg2008_teqp provisional (teqp library runtime-only); issue #188 |
| T-19 | Special family to provisional: solids, polymers, HOC dimer, HF hexamer | T-10, T-03b, T-15 | merged #200 (542c6fc) 2026-10-23: ideal_solid checks, hoc_dimer rebound to Ritter & Simons, polymer rows stay experimental (no open data); issue #190 |
| T-11..T-14 | Validation data sweeps per family (cubic, gamma-phi, Helmholtz/K-value, electrolytes): literature cases with citations, data-only PRs | T-01 | all merged: T-11 #131, T-12 #132, T-13 #135, T-14 #147 (2026-10-21) |

Dispatch: T-01 alone; then T-02, T-03, T-04, T-05, T-07, T-11, T-12, T-13 in parallel (disjoint files); then T-06, T-08, T-09, T-14; then T-10; then the catalogue freeze (status audit).
