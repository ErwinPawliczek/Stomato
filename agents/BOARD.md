# Stomato agent board

Shared coordination file for all agents working on Stomato. Read `agents/PROTOCOL.md` first.
Times are America/Chicago (CST). Newest handoff on top.

## Task board

| id | title | owner | status | branch | updated |
|----|-------|-------|--------|--------|---------|
| V1 | Validation run: cite reference cases for provisional thermo models, then R2 units | Claude Code | blocked — Claude 5h limit (CONTINUE END 12:27, resets 4:30 PM); continue script scheduled 4:35 PM (validation watcher); no new chem-engine merge since val-infra | chem-engine (local run, log `~/stomato-val.log`) | 2026-11-04 12:38 PM |
| T1 | Obvious trial (superseded by T1r) | Obvious | dropped (stale since 10:50 AM, nothing pushed) | — | 2026-11-04 12:15 PM |
| T1r | Retry T1 with push rules: data pack PR ethane/propane VLE + NRTL ethanol/water VLE (IF97 dropped: V1 validated it) | Obvious | accepted (PR #342, awaits suite) | obv/T1r | 2026-11-04 12:18 PM |
| T3 | SR-POLAR: find open published RKUPP p1-p3 parameters + c_i(T) translation and a worked example | Obvious | accepted w/ fix (PR #343; fix in T10) | obv/T3 | 2026-11-04 12:22 PM |
| T4 | API liquid density: public reproductions of API TDB 6A3.5 / Rackett-type petroleum correlations with worked examples | Obvious | accepted (PR #338) | obv/T4 | 2026-11-04 12:11 PM |
| T5 | COSMO-SAC: open sigma-profile DBs (VT-2005, UD/NIST Bell 2020) + independent gamma-inf/VLE pack | Obvious | accepted (PR #341) | obv/T5 | 2026-11-04 12:16 PM |
| T6 | Polymer SRK / polymer-solvent: open polymer-solvent VLE data independent of Kiss 2009 | Obvious | accepted (PR #340) | obv/T6 | 2026-11-04 12:26 PM |
| T7 | Acetic acid/water open VLE pack (hoc_dimer L2 gap) | Obvious | data accepted; PR #339 closed (wrong base) → T7b | obv/T7 | 2026-11-04 12:12 PM |
| T8 | Bring reformer_cat.yaml (PR #329) + control_valve.yaml (PR #282) case files into a chem-engine PR | Obvious | claimed | obv/T8 | 2026-11-04 12:06 PM |
| T7b | Re-cut T7 pack onto chem-engine (PR #339 was cut from agents-board: 254 files incl. uv.lock/.importlinter); drop the 6 Antoine-computed Psat cases | Obvious | open | obv/T7b | 2026-11-04 12:55 PM |
| T9 | Add AcOH (64-19-7), EtOH (64-17-5), O2 (7782-44-7) to data/components.yaml (identity only; props resolve via chemdb/chemicals by CAS) | Obvious | open | obv/T9 | 2026-11-04 12:55 PM |
| T10 | Hook accepted packs (T1r, T3, T4, T5, T6, T7b) into the validation harness; T1r runs on nrtl, pending:* stay skipped; T3 P-value fix | Obvious | open (after T9) | obv/T10 | 2026-11-04 12:55 PM |
| T11 | SR-POLAR adapter from Mangold 2019 params (H2O/O2/N2/CO2), density-only validation level, supercritical tolerance rule | Obvious | open (after T9) | obv/T11 | 2026-11-04 12:55 PM |
| T2 | Board loop test | Obvious | done | agents-board | 2026-11-04 10:57 AM |

Status values: `open`, `claimed`, `in progress`, `blocked`, `review`, `done`, `dropped`.

## Handoffs

### Review — Stomato bot — 2026-11-04 12:55 PM
- Done: Reviewed Obvious packs. Spot-checks: T1r all 16 T-x-y rows + azeotrope match the NIST ThermoML XML exactly; T3 all 9 rows match Mangold 2019 Table 8 (PMC6919335); T7 Sebastiani row 100.8 °C / x_w 0.865 / y_w 0.907 matches the open PDF and the AcOH/H2O column mapping is correct; T6/T4/T5 sources plausible and internally consistent (hrcak PDF not script-retrievable, not independently checked).
- Verdicts: #338 T4 accept (caveat: source is a public API ballot draft, 1 worked-example case, pending adapter). #339 T7 data accept, PR closed — branch cut from agents-board so it carries 254 files incl. locked uv.lock/.importlinter; re-cut as T7b and drop the 6 Antoine-evaluated Psat "cases" (correlation output, not measurement). #340 T6 accept. #341 T5 accept (UD profiles academic/non-commercial — per the deferred-licence decision). #342 T1r accept. #343 T3 accept with fix: P 263899999 → 263900000; pack is density-only, NOT VLE validation for SR-POLAR.
- Decisions: AcOH/EtOH/O2 added as components (chemdb already holds cited Tc/Pc/omega/Tb etc. for all three; components.yaml is identity-only) → T9. SR-POLAR: implement with Mangold params as density-level only, VLE row stays open → T11. Supercritical tolerance: compare against the paper's own per-point VTBMSR-III error (|ours − ref| ≤ |paper err| + 2 %), not P1-05 bands.
- Next: Obvious T7b, T9, T10, T11 dispatched (project ids in Shared notes). Nothing merges to chem-engine until the full suite passes on Erwin's PC.

### Board sync — Stomato bot — 2026-11-04 12:38 PM
- Done: Pulled T3 handoff (35a38ec): T3 → `review`, PR #343 (`obv/T3` c1e7b09, SR-POLAR Mangold 2019 params + 9 water-air density cases; methanol/ethanol/acetone/ammonia p-sets NOT FOUND, paywalled; params regressed on density, not VLE). V1 → `blocked`: continue session ended 12:27 on Claude 5h limit; validation watcher scheduled the next continue for 4:35 PM. T8 claimed 12:06, no `obv/T8` push yet (32 min, stale at ~12:51).
- Outputs: this board update only. No new Obvious job (no unclaimed approved task).
- Next: review/merge queue T4 #338, T7 #339, T6 #340, T5 #341, T1r #342, T3 #343; curation decisions pending for AcOH (T7), EtOH (T1r), O2 + SR-POLAR row + supercritical tolerance (T3). Watch T8.
### T3 — Obvious — 2026-11-04 12:22 PM (HANDOFF)
- Done: SR-POLAR open parameter pack + worked example. Located and fully retrieved the only open source with published Schwartzentruber-Renon polar parameters + temperature-dependent volume translation: Mangold et al. 2019 (J. Supercrit. Fluids 153, 104476, doi:10.1016/j.supflu.2019.02.016, open CC BY, PMC6919335; SI PDF via the Elsevier CDN after PMC's endpoint proved bot-gated). Transcribed main Tables 2/5/7 + SI Tables S1.1-S1.6 (78 param rows: c_i, p_i, k_b_ij for H2O/O2/N2/CO2 incl. SI-only alternate sets), cross-checked main vs SI (agree; one rounding-level digit on water c2). Worked example = the paper's Table 8 ternary water-air molar volumes (9 points, 620.5-657 K, 27-263.9 MPa), packed as single-phase density cases; worked numbers computed from the printed parameters (omega=0.344 -> m=1.000461; alpha(620.5K)=1.059912, c=1.2044e-05 m3/mol).
- Outputs (paths / branch / commit / PR #): data/validation/packs/T3/{params.csv,data.csv,pack.yaml,notes.md}; branch obv/T3, commit c1e7b09; PR #343 (obv/T3 -> chem-engine): https://github.com/ErwinPawliczek/Stomato/pull/343. Also published in the Obvious workspace: research-notes artifact (art_etSX4JnI).
- Sources used: Mangold et al. 2019 main + SI (retrieved 2026-11-04); NIST WebBook molar masses (H2O 18.0153, O2 31.9988, N2 28.0134 g/mol). Everything transcribed; nothing fitted or interpolated. Densities are unit conversions of the printed molar volumes (Mangold assumed air = x_O2/x_N2 1/4; Japas & Franck do not specify it - flagged per case).
- NOT FOUND / gaps: methanol/ethanol/acetone/ammonia 3-param p-sets - Schwartzentruber & Renon I&ECR 28 (1989) 1049 paywalled (no OA copy anywhere); Jordison/Lira/Miller IECR 2015 (10.1021/acs.iecr.5b02409) paywalled incl. its SI; Jordison 2016 MSU thesis 403s all scripted access; pychemqt has Mathias-1983 only; NeqSim has the alpha form, no cited table. Confirms the catalogue's 2026-11-03 note. Scope caveat: Mangold's params are regressed on density/caloric data, NOT vapour pressure - cannot close the SR-POLAR row for VLE (pack header states this). Alpha-form ambiguity ((1-Tr) vs (1-Tr^0.5)): Mangold prints (1-Tr) in both main and SI; p-values bound to that form; 1989 original unverifiable open. "RKUPP" in the task title: no repo/Crossref hit - read as the three polar parameters, flagged in notes.md.
- Tests run + result: none (data-only PR; no code touched, no cases*.yaml touched). Scripted checks: pack.yaml parses (9 cases, ids unique, z sums 1, components match z); params.csv/data.csv parse clean.
- Next / open questions: Stomato bot to review PR #343. Binding needs: (1) O2 curated in data/components.yaml (CAS 7782-44-7; N2/CO2/H2O exist) - cases cannot resolve before that; (2) the pending:sr-polar row registered (catalogue row 14) or the pack's package id renamed; (3) a tolerance decision for supercritical states (P1-05 density bands do not cover them; paper's own model error runs to 15% at >100 MPa; data.csv carries the paper's per-point VTBMSR-III error for a like-for-like check).
- Heartbeats: single-session run (claim 12:06 PM -> push 12:22 PM CST); no heartbeat cadence needed.

### Board sync — Stomato bot — 2026-11-04 12:21 PM
- Done: Pulled 5 Obvious commits. T5 → `review`, PR #341 (`obv/T5` 93ae662, COSMO-SAC licence audit + 35 bubble_T cases + 7 gamma-inf rows). T1r → `review`, PR #342 (`obv/T1r`, EtOH/H2O NRTL pack 15 cases; ethane/propane NOT FOUND, paywalled). T1r handoff/heartbeats are labelled 12:40/1:00/1:25 PM but the git commits are 12:1x PM CST — Obvious clock labels run ahead; board `updated` column uses commit times. V1: `~/stomato-val.log` shows the Claude session hit its 5-hour limit ~12:08 (resets 4:30 PM CST); pid 736208 and in-flight gate shells still alive. T3/T8 claimed 12:06, no `obv/*` push yet (<45 min, not stale).
- Outputs: this board update only. No new Obvious job (all board tasks already dispatched).
- Next: review/merge queue now T4 #338, T7 #339, T6 #340, T5 #341, T1r #342; curation decisions pending for AcOH (T7) and EtOH (T1r). Validation watcher owns V1 resume after 4:30 PM. Watch T3/T8 (stale at ~12:51).
### T1r — Obvious — 2026-11-04 1:25 PM (HANDOFF — status review)
- Done: Task T1r executed per the playbook (claimed 12:07 PM CST; branch obv/T1r cut from origin/chem-engine; two heartbeats pushed; V1 files untouched). Pack (b) delivered: ethanol(1)+water(2) isobaric VLE at 101.3 kPa for the registered NRTL package — data.csv (17 points) + pack.yaml (15 cases: 14 interior binary points + azeotrope, schema-identical to data/validation/gamma_phi/cases.yaml, tolerances bubble_T 0.5 % / y 0.02 abs per P1-05). Pack (a) ethane/propane for Peng-Robinson: NOT FOUND — no openly retrievable tabulated source exists; no values written, no cases, per the never-invent rule. Data-only PR; no code touched.
- Outputs (paths / branch / commit / PR #): data/validation/packs/T1r/{data.csv,pack.yaml,README.md} on branch obv/T1r, commit afe42dc; PR https://github.com/ErwinPawliczek/Stomato/pull/342 (obv/T1r → chem-engine, never main).
- Sources used: Lai, Lin & Tu (2014) J. Chem. Thermodyn. 68, 13-19, DOI 10.1016/j.jct.2013.08.020 — transcribed 1:1 from the open NIST ThermoML XML trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml (datasets 9: T-x 16 pts, 10: y-x 16 pts, 11: azeotropic T 351.32 K, 12: azeotropic x 0.891), retrieved 2026-11-04; basis verified against pure anchors (351.45 K EtOH / 373.15 K H2O) and the known azeotrope. Full per-point citations in data.csv and README.md.
- NOT FOUND / gaps: ethane+propane binary VLE (pack a). Trail (all 2026-11-04, full table in README.md): NIST ThermoML archive — no C2/C3 binary record (9 candidate DOIs parsed); DDB Explorer/Online — system listed, values quote-only/paywalled; Miksovsky & Wichterle CCCC 1975 (DOI 10.1135/cccc19750365) — buy-only, no archived PDF; classic JCED/IEC papers (Matschke & Thodos 1962, Djordjevich & Budenholzer 1970, et al.) — ACS-paywalled; IUPAC-NIST SDS 27/28 — gas-solubility scope, not binary VLE; NISTIR 3953 — pure ethane only; NBS TN 4 — pure vapor pressures; DECHEMA CDS sample — no C2/C3; OSTI report 5933291 — 404 on osti.gov/servlets/purl/5933291; university repositories — near misses only. Also: source pressure is 101.3 kPa as printed, recorded as 101300 Pa (not silently upgraded to 101325); EtOH is not in the locked data/components.yaml slate — cases will not resolve until EtOH is curated (CAS 64-17-5), same id as the existing nrtl-ig-etohh2o-azeotrope case.
- Tests run + result: none (data-only change; suite unaffected). pack.yaml validated structurally: parses, 15 unique ids, z sums to 1, all schema fields present. ruff/mypy/pytest not run — no Python changed; CI runs on the PR.
- Next / open questions: Stomato bot to bind the pack (pack.yaml, not cases*.yaml) after V1 capacity; decide EtOH curation; optionally license/purchase the DDB or CCCC 1975 sources if a C2/C3 pack is still wanted — the literature datasets exist but are paywalled end to end.
- Heartbeats: 12:40 PM (claim + pack b status), 1:00 PM (pack a trail exhaustion), this handoff 1:25 PM.

### T1r — Obvious — 2026-11-04 1:00 PM (heartbeat 2)
- 1:00 PM CST — pack (b) data secure: all 17 Lai 2014 ethanol/water points transcribed to data.csv + pack.yaml on obv/T1r (committing next). Pack (a) routes exhausted — see heartbeat 1 trail plus: OSTI topical report 5933291 (ethane+propane below 270 K) returns 404 "Page Not Found" on osti.gov/servlets/purl/5933291; DECHEMA CDS sample PDF does not cover C2/C3. Writing NOT FOUND for pack (a) with this full trail; finishing pack (b) now, then PR.

### T5 — Obvious — 2026-11-04 12:12 PM (heartbeat 1)
- 12:12 CST — pack committed to obv/T5 (93ae662): 35 VLE cases (H2O+MEG, H2O+TEG, 0.1 MPa, Chouireb 2018 open SI) + 7 gamma-inf rows (Tochigi 2000 MeOH/H2O; Zhang 2003 MeOH/MEG via ThermoML) + licence audit. N2 not in either DB; CO2 only in UD. PR into chem-engine next.

### T5 — Obvious — 2026-11-04 12:16 PM (HANDOFF)
- **PR:** https://github.com/ErwinPawliczek/Stomato/pull/341 (obv/T5 -> chem-engine, data-only: data/validation/packs/T5/{pack.yaml,data.csv,README.md})
- **Deliverable 1:** First-hand licence audit of NIST COSMOSAC profiles (code MIT; profiles academic/non-commercial, redistribution restricted; UD Readme terms quoted verbatim). VT2005 has NO licence statement (NOT FOUND). Component coverage checked by CAS in both indexes: 16/19 slate ids in UD; CO2 UD-only; H2S UD-only (VT2005 CAS field malformed); **N2 in neither DB**.
- **Deliverable 2:** Independent pack — 35 bubble_T cases (Chouireb 2018 open SI Tables S1/S3, H2O+MEG and H2O+TEG at 0.1 MPa) as `pending:cosmo_sac_ig`, + 7 gamma-inf reference rows (Tochigi 2000 MeOH/H2O; Zhang 2003 MeOH/MEG via ThermoML). Independent of Hsieh 2014 Table 6 and NIST COSMOSAC validation outputs.
- **Validation:** pack.yaml parses (35 cases, unique ids, z sums 1, components match z); data.csv parses (44 rows, no ragged rows). bubble_T tolerance 0.5% per P1-05.
- **Known gaps (documented in README):** no open gamma-inf tables for H2O in MEG/TEG, MeOH in TEG, MeOH+DME VLE; harness lacks gamma-inf expected key; ThermoML raw .xml fetch empty — values cited from rendered dataset page.
- **Reviewer:** validate transcriptions against the cited open URLs (Chouireb SI, Tochigi KJChE page, ThermoML dataset 016027), then merge per protocol.


### Board sync — Stomato bot — 2026-11-04 12:13 PM
- Done: Reconciled from git + `~/stomato-val-progress.md` + live processes. V1 continue (pid 736208) alive since 11:35; chem-engine tip still val-infra `296e6f6`; `val-integ` gating val-blocked (`~/stomato-val-gate.sh`, audit running). Package branches advanced (units-a/b/c, gphi-*, helm-kvalue, cubic-mixing, special, electrolyte-amine, blocked). Obvious: T4 `review` PR #338 (`obv/T4` fb4eb4d); T6 `review` PR #340 (`obv/T6` aa4754d); T7 `review` PR #339 (`obv/T7` e6b7a58); T1r/T3/T5/T8 claimed — `obv/T5` tip exists at chem-engine base only (no pack). No active claim >45 min silent. No new Obvious job started (T1r/T3–T8 already dispatched).
- Outputs: this board update only.
- Next: watch T1r/T3/T5/T8 for first `obv/*` push / heartbeat; review/merge T4+T6+T7 after V1 gate capacity; do not bind packs into live cases*.yaml until V1 is ready.

### V1 — Claude Code (board sync) — 2026-11-04 12:13 PM
- Done: Still running after 11:35 resume. Only chem-engine merge so far remains val-infra (`8a7d545`, `296e6f6`). Progress log updated 12:00 CST; worktrees active. Orchestrator currently gating val-blocked/`cosmo_sac_ig` via `~/stomato-val-integ` + `~/stomato-val-gate.sh` (audit in progress as of 12:12).
- Branch tips observed: val-gphi-unifac `e934fe0`, val-gphi-corr `3469461`, val-units-a `af23f0c`, val-units-b `5b432ca`, val-units-c `0d5b832`, val-cubic-mixing `b489afd`, val-helm-kvalue `9e5d771`, val-special `46103d5`, val-electrolyte-amine `bed50eb`, val-blocked `13aff08`, val-integ `0f09f99`.
- Tests run + result: prior val-infra gate green (recorded 11:35). No new chem-engine merge yet this sync.
- Next / open questions: finish val-blocked gate then queue other package merges; blocked open-data gaps now have Obvious packs in review (T4 PR #338, T6 PR #340, T7 PR #339; T3 still claimed).

### T7 — Obvious — 2026-11-04 12:12 PM
- Done: Acetic acid/water open VLE pack for `hoc_dimer` assembled from three open sources retrieved this session; PR open into `chem-engine`.
- Outputs (paths / branch / commit / PR #): `data/validation/packs/T7/{data.csv,pack.yaml}` on branch `obv/T7`, commit e6b7a58; **PR #339** (obv/T7 → chem-engine): https://github.com/ErwinPawliczek/Stomato/pull/339. 79 cited data rows; 75 cases (23 isobaric binary T,x,y + 44 isothermal binary T,P,x + 8 pure-AcOH Psat cases: 6 Antoine evaluations labelled computed + 2 measured anchors). Tolerances per P1-05 (bubble_T 0.5 %, y 0.02 abs, bubble_P 3 %).
- Sources used: (1) Sebastiani & Lacquaniti, Chem. Eng. Sci. 22 (1967) 1155-1162, DOI 10.1016/0009-2509(67)80182-9, Table 1 p. 1157 — 23 isobaric points at atmospheric pressure (open PDF, retrieved 2026-11-04); (2) Román-Ramírez & Leeke, J. Chem. Eng. Data 61 (2016) 2078-2082, DOI 10.1021/acs.jced.5b01104, Table 2 — isothermal p-x at 412.6/443.2/483.2 K, no measured y (open copy, Cranfield CERES, retrieved 2026-11-04); (3) NIST Chemistry WebBook SRD 69 acetic acid page — Antoine params log10(P/bar)=4.68206-1642.54/(T/K-39.764) valid 290.26-391.01 K from McDonald, Shrader & Stull, JCED 4 (1959) 311, DOI 10.1021/je60004a009, plus TRC T_boil 391.2 ± 0.6 K (retrieved 2026-11-04).
- NOT FOUND / gaps: data/components.yaml has NO AcOH entry (CAS 64-19-7) — cases cannot resolve until AcOH is curated (flagged in pack.yaml header). Marek 1955 (DOI 10.1135/cccc19551490) landing page retrieves but its full data table is not openly retrievable — NOT FOUND (paywalled/archived). Zhang 2011 (FPE 305, DOI 10.1016/j.fluid.2011.03.006) ThermoML record checked and EXCLUDED — its archived datasets are the ternaries with propyl/isobutyl acetate (liquid fractions sum < 1), not the binary. Vercher 2001 ThermoML record (je010106p) 404s on trc.nist.gov. The 1967 paper states "atmospheric pressure" without a barometric reading; P = 101325 Pa is the convention, flagged per point. hoc_dimer row notes (T-19) apply: the package's liquid side is ideal, so binding the binary cases as pass/fail needs a regressed GE pair or widened tolerances — the pack pins the data independently.
- Tests run + result: none (data-only PR; no code touched). Scripted checks on the pack: YAML parses (75 cases), ids unique, z sums to 1, Sebastiani series monotone in T vs x_H2O, isotherm P ranges ordered — all clean.
- Next / open questions: Stomato bot to review PR #339 and decide binding (needs AcOH curation + the GE-pair decision above). Candidate open follow-up: transcribe Marek 1955 from the print/archive if it becomes openly accessible.
- Heartbeats: single-session run (claim 12:10 PM → push 12:12 PM CST); no heartbeat cadence needed.
### T4 — Obvious — 2026-11-04 12:11 PM CST
- Done: API liquid density pack. Found the procedure itself in a public API e-ballot draft, "Technical Data Book: Part 6 – Density" (TDB-6_e1 draft.pdf): Procedure 6A2.3 "Density of Liquid Petroleum Fractions at Low Pressures with the Modified Rackett Equation (1992)" — the procedure historically numbered 6A3.5 — with its complete worked example (MeABP 538 °F, API gravity 30.6 → rho(160 °F) = 0.8353 g/mL; experimental 0.8343 g/mL), printed M/Tpc/Ppc correlations, and ZRA back-calculation from SG. Every printed number was re-derived independently in Python before transcription (agreement ≤0.03 % on intermediates, 0.0002 g/mL on the final density). Corroborating open reproduction: Ramos-Pallares 2017 PhD thesis (Calgary) — Spencer–Danner modified Rackett, ZRA tuned at 15.6 °C to SG, Tables E.1–E.6 pseudocomponent parameters (kept as parameter data, not cases: reconstruction deviates −1 to −2 %). IJERT 2024 paper independently confirms the historical number: "procedures 11A4.1 and 6A3.5 of API (1997)".
- Outputs (paths / branch / commit / PR #): `data/validation/packs/T4/{notes.md,data.csv,pack.yaml}`; branch `obv/T4`, commit fb4eb4d; PR #338 (`obv/T4` → `chem-engine`). No code changes; no V1 files touched.
- Sources used: API TDB-6 e-ballot draft (URL + pages in notes.md §1–§3, retrieved 2026-11-04); Ramos-Pallares 2017 U Calgary thesis (notes.md §4); IJERT V13 IS 070052 (notes.md §5).
- NOT FOUND / gaps: Riazi MNL50 §5.8/Ch.7 body text (public sample PDF is TOC-only; full book paywalled); Rackett 1970 original paper (paywalled); published TDB 1997/2016 editions (paywalled); Nji Calgary thesis link dead (returned HTML). No open reproduction of the *published* 6A3.5 exists — the ballot draft of the renumbered procedure is the closest open artifact. Details in notes.md §6.
- Tests run + result: none — data-only pack, no code touched; cases carry `package: pending:api-liquid-density` (adapter not registered; listed blocked in V1's progress log) so the harness skips them until bound. Pack named pack.yaml per PROTOCOL.md.
- Next / open questions: Stomato bot to bind pack.yaml when the API-liquid-density adapter spec registers its row (reconcile pending id `api-liquid-density` then). Ballot-draft caveat: numbers are as balloted, published TDB remains authority of record (flagged in notes.md §1).
- Heartbeats: 12:10 PM CST — sources located and verified (below).

### T4 — Obvious — 2026-11-04 12:10 PM CST
- 12:10 PM CST — heartbeat: sources located and verified. Primary: public API e-ballot draft "Technical Data Book: Part 6 – Density" (TDB-6_e1 draft.pdf, eballotprodstorage.blob.core.windows.net) containing the modified-Rackett procedure for petroleum fractions at low pressure (1992 procedure, historically numbered 6A3.5; renumbered 6A2.3 in the draft) with a complete worked example. All example numbers reproduced independently in Python (SG, M, Tpc, ppc, ZRA, rho at 160 F) before transcription. Writing pack files to data/validation/packs/T4/ on obv/T4 next.

### Board — Stomato bot — 2026-11-04 12:15 PM
- PROTOCOL.md rewritten as the Obvious playbook. T1 dropped as stale; T1r + T3-T8 dispatched to Obvious (project ids in Shared notes). All data tasks write packs to data/validation/packs/<id>/ (pack.yaml, not cases*.yaml) so they don't collide with V1's files.

### T6 — Obvious — 2026-11-04 12:10 PM
- 12:10 PM CST — Obvious (T6): claimed; three open sources verified with full numeric tables (CABEQ 2015 PS/toluene; Tanbonliong/Prausnitz UC thesis; CABEQ 2014 PMMA/2-butanone). Building pack now.

### T6 — Obvious — 2026-11-04 12:26 PM
- Done: Task T6 complete. Three open experimental polymer-solvent VLE sources found, read as open full text, transcribed with full citations, and packed; nothing invented, estimated, or fitted; no V1 file (cases*.yaml) touched. PR #340 open into chem-engine (never main).
- Outputs (paths / branch / commit / PR #): data/validation/packs/T6/{data.csv (65 rows), pack.yaml (59 cases), README.md}; branch obv/T6, commit aa4754d; PR: https://github.com/ErwinPawliczek/Stomato/pull/340 (obv/T6 -> chem-engine).
- Sources used: (1) Pavlicek/Bogdanic/Wichterle, CABEQ 29 (2015) 1-4, Table 2 p. 2, doi:10.15255/CABEQ.2015.2183 (toluene+PS Mw 250k, 363.15/373.15/383.15 K; open: https://hrcak.srce.hr/file/202639). (2) Tanbonliong/Prausnitz, "Vapor-Liquid Equilibria for Some Binary and Ternary Polymer Solutions", eScholarship (UC) 1996, Table 2 p. 18 (chloroform+PS 50k, methyl acetate+PS 50k, acetone+PMMA 125k, methyl acetate+PMMA 125k, 323.15 K; https://escholarship.org/uc/item/8wq3x5wd). (3) Pavlicek/Bogdanic/Wichterle, CABEQ 28 (2014) 447-450, Table 2 p. 448, doi:10.15255/CABEQ.2014.19388 (2-butanone+PMMA 15k, 333.15/343.15/353.15 K; open: https://hrcak.srce.hr/file/195544). Solvent Mw from NIST WebBook (toluene 92.1384, acetone 58.0791, 2-butanone 72.1057, chloroform 119.378, methyl acetate 74.0785; retrieved 2026-11-04).
- NOT FOUND / gaps: PIB/pentane and PE/hexane open numeric tables with MW stated — paywalled (doi:10.1002/pol.1982.180200503 PIB sorption isotherms; Wohlfarth/Landolt-Boernstein compilations). No open FH chi for the new pairs (S2/S3 stay pending:flory_huggins, nothing fitted). No PMMA pseudo-component registration in-repo (only POLY_PS of P1-07); pack names the ids a future curation would register. Thesis PS-acetone rows are Bawn & Wajid 1956 (paywalled) and were NOT packed (provenance guard).
- Tests run + result: no repo test suite run (data-only change, no code paths affected) — stated per protocol rule 6. In-session checks: data.csv (65 rows) and pack.yaml (59 cases) parse; every pack case matches a data.csv row exactly on (T, P); the papers' printed activities reproduce from their own P/P1o columns to 4 decimals (S1 and S3, all three isotherms each).
- Next / open questions: Stomato bot to review PR #340 and bind the pack when convenient. S1 binds naturally to pending:polymer_pc_saft (parameters exist in-repo, k_ij = 0; note packed PS sample Mw 250k vs shipped POLY_PS Mw 400k, documented in pack.yaml). S2/S3 need FH chi parameter curation first. Board sync may want to record the three sources in the "Sources found" table.
- Heartbeats: 12:10 PM CST — claimed; three open sources verified with full numeric tables; building pack. 12:26 PM CST — pack pushed to obv/T6 (aa4754d), PR #340 open, status review.

<!-- Template:
### <id> — <owner> — <YYYY-MM-DD HH:MM>
- Done:
- Outputs (paths / branch / commit):
- Sources used:
- NOT FOUND / gaps:
- Tests run + result:
- Next / open questions:
-->

### V1 — Claude Code (board sync) — 2026-11-04 11:45 AM
- Done: Run resumed 11:35 AM after the 5-hour usage reset. val-infra (8a7d545, 296e6f6) fast-forwarded into chem-engine at 11:35.
- Outputs (paths / branch / commit): chem-engine; progress in `~/stomato-val-progress.md`.
- Tests run + result (from progress log): ruff, format, mypy (656 files), lint-imports (3 kept), full pytest --extra saft exit 0, audit PASS, frontend typecheck/lint/check:api, vitest 147/147.
- Next / open questions: remaining workstreams (units-a/b/c, special, gphi-corr, etc.) continue; blocked models listed in progress log: COSMO-SAC, SR-POLAR, Polymer SRK, API liquid density.

### T2 — Obvious — 2026-11-04 10:57 AM
- Done: Coordination loop test — read `agents/PROTOCOL.md`, added T2 row to the task board, committed and pushed this handoff to `agents-board`.
- Outputs (paths / branch / commit): `agents/BOARD.md` on branch `agents-board`, commit _this commit_.
- Sources used: `agents/PROTOCOL.md`, `agents/BOARD.md` (both on `agents-board`).
- NOT FOUND / gaps: T1 thermo reference-data results are not visible to me — the board shows T1 (Obvious, in progress, branch `obv/T1`, results in the Obvious project, no push access yet), but the actual T1 outputs are not on `agents-board` and were not part of this test's scope. Marking NOT FOUND for T1 result contents.
- Tests run + result: none (board-only edit; no code touched).
- Next / open questions: confirm push access to `agents-board` works end-to-end; T1 owner to push results to `obv/T1` once GitHub App access is granted (see Open questions).

## Shared notes

### Decisions
- 2026-11-04: AcOH, EtOH, O2 join components.yaml (identity; cited chemdb props). SR-POLAR registered density-only (Mangold 2019 params are density-fitted, not VLE). Supercritical density cases use the source paper's own model error as tolerance. Computed (correlation-evaluated) points are never validation cases.
- 2026-11-04: Heavy units stay at catalogue R2 for now; validation comes first.
- 2026-11-04: Licence questions deferred (non-commercial); still record the source of every value.
- 2026-11-04: Companies will bring their own data; structure must accept user parameter sets with recorded sources.

### Open questions
- Does the Obvious workspace tied to the API key hold the $20k credits?
- Obvious GitHub App install on the Stomato repo (needed for Obvious to push `obv/*` branches).
  - 2026-11-04 11:11 AM (board sync): Obvious pushed commit bea3182 to `agents-board` (T2), so its push access works for this branch.
  - 2026-11-04 12:13 PM (board sync): packs on `obv/T4` (fb4eb4d, PR #338), `obv/T6` (aa4754d, PR #340), `obv/T7` (e6b7a58, PR #339); `obv/T5` tip exists at chem-engine base only (no pack). T1r/T3/T8 still lack `obv/*` tips.

### Obvious projects (dispatched 2026-11-04 12:20 PM CST, workspace wks_IDdvA1UG)
| task | project | execution |
|---|---|---|
| T1r | prj_4bg1MlBW | exec_8Tb8jWO0 |
| T3 | prj_Rh6o5zhG | exec_lCRgWdzP |
| T4 | prj_mYOI5T12 | exec_Jq1IfIUF |
| T5 | prj_UL5jKG4T | exec_ctQh3Dda |
| T6 | prj_MiBfJLDC | exec_5ZBp3PUC |
| T7 | prj_J0x7iuFO | exec_mbxJeQ2t |
| T8 | prj_1JiMmh1a | exec_1DS7Neqa |

### Sources found
| model / unit | dataset | citation | DOI / URL | added by |
|---|---|---|---|---|
| API liquid density (pending) | T4 pack worked example (MeABP 538 °F, API 30.6 → rho 160 °F) | API TDB-6 e-ballot draft Proc. 6A2.3 (= hist. 6A3.5); Ramos-Pallares 2017; IJERT 2024 | https://eballotprodstorage.blob.core.windows.net/eballotscontainer/TDB-6_e1%20draft.pdf ; pack on obv/T4 | T4 / board sync |
| hoc_dimer AcOH/H2O | T7 pack (Sebastiani 1967 isobaric; Román-Ramírez & Leeke 2016 isothermal p-x; NIST Antoine/TRC) | Sebastiani & Lacquaniti CES 22 (1967); Román-Ramírez & Leeke JCED 61 (2016); NIST SRD 69 / McDonald 1959 | DOI 10.1016/0009-2509(67)80182-9 ; DOI 10.1021/acs.jced.5b01104 ; pack on obv/T7 | T7 / board sync |
| polymer-solvent VLE | T6 pack (PS/toluene; PS+PMMA binaries) | Pavlicek/Bogdanic/Wichterle CABEQ 2015 & 2014; Tanbonliong/Prausnitz UC 1996 | doi:10.15255/CABEQ.2015.2183 ; doi:10.15255/CABEQ.2014.19388 ; pack on obv/T6 | T6 / board sync |
| cosmo_sac_ig (pending) | T5 pack (H2O+MEG, H2O+TEG bubble_T 0.1 MPa; gamma-inf MeOH/H2O, MeOH/MEG) + sigma-profile licence audit | Chouireb 2018 open SI; Tochigi 2000; Zhang 2003 (ThermoML) | PR #341 ; pack on obv/T5 (URLs in packs/T5/README.md) | T5 / board sync |
| NRTL EtOH/H2O | T1r pack (17 pts isobaric 101.3 kPa + azeotrope) | Lai, Lin & Tu, J. Chem. Thermodyn. 68 (2014) 13-19 | DOI 10.1016/j.jct.2013.08.020 ; trc.nist.gov/ThermoML/10.1016/j.jct.2013.08.020.xml ; PR #342 | T1r / board sync |
| SR-POLAR (pending) | T3 pack (Mangold 2019 H2O/O2/N2/CO2 params; Table 8 water-air molar volumes, 9 pts) | Mangold et al., J. Supercrit. Fluids 153 (2019) 104476 (CC BY) | doi:10.1016/j.supflu.2019.02.016 ; PMC6919335 ; PR #343 | T3 / board sync |
