# T-08: Model advisor — fluid-package recommendation for the agent and the UI

- **Phase:** Thermo catalogue, wave 2
- **Depends on:** T-01..T-05 (catalogue rows with applicability and status)
- **Packages you may edit:** `ngdesign.thermo` (new `advisor.py`), `ngdesign.agent` (`tools.py`: one new tool `recommend_thermo`; `loop.py`: one sentence in the system prompt), `ngdesign.api` (`routes_meta.py`: `GET /api/thermo/recommend`), `tests/thermo/`, `tests/agent/`, `tests/api/`, `openapi.json` + `schema.d.ts` (regenerated); the frontend picker is a separate frontend-only PR (the CI guard forbids mixing)
- **Contract change:** yes — new route (orchestrator applies `contract-change`)
- **Benchmark delta expected:** none

## Goal
The catalogue is useless without the wizard. Given a flowsheet (its slate, feed conditions,
expected phases) the advisor returns ranked property methods with the reason and the status, and
says "no parameters for pair X/Y" rather than ranking a method that would silently assume ideality.

## Files
- `thermo/advisor.py`: `recommend(fs: Flowsheet) -> list[Recommendation]` with
  `Recommendation(id, score, reasons: list[str], warnings: list[str], status)`. Inputs derived from
  the flowsheet: component classes (via the catalogue's class vocabulary and `chemicals` identity:
  hydrocarbon, light gas, water, alcohol/glycol, amine, acid gas, electrolyte), max/min feed T and
  P, presence of water (free-water / VLL), polarity, electrolytes. Rules table (data, in the module,
  cited): Carlson 1996 (*Chem. Eng. Prog.* 92(10) 35–46) decision tree; GPSA for natural gas
  (PR/SRK, GERG when density matters at high P); Kohl & Nielsen for amine/physical solvents;
  Prausnitz, Lichtenthaler & de Azevedo ch. 9 for activity models by pressure; Aspen/HYSYS
  selection charts as secondary (cite the published charts, not internal data). Each rule yields a
  score contribution and a reason string. Missing binary parameters for a gamma-phi candidate are a
  warning that demotes it below any EOS candidate that covers the pair. `experimental` rows never
  rank; `provisional` rows rank with a warning.
- Agent tool `recommend_thermo(project)`; API route returning the same list for the current
  project; one line in the agent system prompt telling it to call the tool before changing
  `flowsheet.thermo`.
- Tests: the slice (sour gas + TEG) → `pr`/`srk` first with the water warning; the MDEA loop →
  `amine_ke`/`amine_enrtl` first; a methanol/water column at 1 bar → gamma-phi NRTL first, cubics
  demoted with the polarity reason; a pair without NRTL parameters → the warning and the demotion;
  an `experimental` row never appears; determinism.

## Acceptance criteria
- [ ] Route and tool return identical rankings; tests above pass; openapi/schema regenerated, `check:api`/`typecheck` green
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green; nothing outside the listed packages changed
