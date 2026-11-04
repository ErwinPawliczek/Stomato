# UI gaps: what works end to end, and what is still waiting

Audit date: 2026-11-03, on `chem-engine` after the provenance, multi-project,
unit-picker and agentic-layer merges.

Method: a headless-browser click-through (Playwright, Chromium) of every
screen against a real backend (scripted agent, fresh SQLite database), in all
three palettes, plus the frontend searched for disabled, stubbed, mocked,
placeholder and hard-coded features. Every fix below has a test; the commits
on `chem-engine` after `c2ec285` carry the details.

## Screen by screen

| Screen | State | Notes |
|---|---|---|
| Home: project list | **Works** | Cards draw each project's own flowsheet (was one hard-coded drawing); Open, Rename, Duplicate, Delete, **Export** (new: the JSON Import reads back). |
| Home: New project | **Works** | Blank or any template. The form says templates are loading while GET `/api/templates` warms up (~3 s cold) and still creates a blank project. |
| Home: Import | **Partly** | Stomato `.json` works. HYSYS, Aspen Plus and DWSIM stay disabled ("planned"): there is no importer in the backend. |
| Flowsheet: unit picker, hex grid | **Works** | Categorised palette, drag-drop or click to add, snap grid, pan/zoom, arrow-key moves. |
| Flowsheet: connecting streams | **Works** (new) | Click a unit to select it (ports, what is on each, Connect into/from, Delete). Connect stream: free outlet or a battery-limit feed (T, P, flow, composition) to free inlet or a product. Ports come from GET `/api/v1/catalogue/units`. |
| Flowsheet: deleting | **Works** (new) | Delete a unit (with its streams and placements, the backend's semantics) or a stream. |
| Flowsheet: editing values | **Works** | Unit params, feed T/P/flow, and feed compositions (new: `C1=0.9, C2=0.1`, checked to sum to 1). |
| Flowsheet: thermo model | **Works** (fixed) | Reads GET `/api/thermo/models`; models the solve refuses are listed disabled with the reason (was: any of ~160 names, saving fine and failing at solve). |
| Flowsheet: design specs | **Works** (new) | List, add, delete; persisted by Save; outcomes shown in Results. |
| Results | **Works** (fixed) | Last solve kept across tab switches; failed solves name each unit, stage and reason; design-spec outcomes; trace links render as links again (a CSS rule had turned them into buttons and cut off Info). |
| Trace | **Works** (fixed) | Traced the backend's `default` project, which a fresh database does not have ("no default project"); now traces the open project. |
| Drawings: PFD, P&ID, plot plan | **Works** | A 422 reads "P&ID cannot be drawn yet: unit E-901 has no connected streams to size from" instead of the raw HTTP error. |
| Drawings: Isometrics | **Works** (new) | Was a placeholder. Line picker, the iso sheet SVG, title block, BOM and cut list from `/views/iso`. |
| Agent | **Works** (fixed) | Works on the open project (with none open it offers the projects; it used to talk to the absent `default` project). Text and tool calls in order (text used to run together after all calls). Conversations reopen and delete; the latest reopens on return. A stale conversation id (404) starts a new one instead of failing every send. Tool-call diffs, History undo/redo and the live change stream were already working. |
| Equipment | **Works** (fixed) | 68 kinds showed names made from the id ("Cstr", "Fcc"); they now use the catalogue's names, categories, summaries and ports. Generic symbols for those kinds are a unit-visuals task (out of scope here). |
| Sheet | **Waiting** | A plain in-memory grid. See "Decisions" below. |
| Palettes (Permian, Blueprint, Mint Graphite) | **Works** | All screens checked in each. |

## Backend fixes made in this pass

| Defect | Fix | Test |
|---|---|---|
| A blank project (the New project default) made GET `.../views/pfd.svg` **500** (`max()` of no unit sizes) | The PFD draws an empty sheet | `tests/api/test_blank_project_views.py` |
| A blank project made the plot plan, re-route and isometrics **500** (router `ValueError`) | `pipeline.route` maps router input errors to `UndrawableProjectError` → 422 with the reason, like `build_pid` | same |
| The agent's `render` tool returned `/api/views/{view}.svg` (the default project) whatever project it worked on | A stored project gets `/api/v1/projects/{id}/exports/{view}.svg` | `tests/agent/test_tools.py` |

`stomato-mcp` was verified on both transports against a live API database:
stdio and streamable HTTP (`--transport http --port N`, path `/mcp`) both
initialize, list 36 tools, solve, read results, and a `set_cell` + `undo` shows
up in GET `/api/v1/projects/{id}/changes`. Bearer auth (`STOMATO_API_TOKENS`)
gives 401 without a token and works with one. Note: it opens the database
directly (`STOMATO_DATABASE_URL`), it does not call the REST API.

## Still waiting (needs a decision or backend work)

1. **Sheet.** The grid keeps values in memory only. The backend has model
   variables as cells (GET/PUT `/api/v1/projects/{id}/cells/{address}`), but no
   free-form spreadsheet with formulas or storage (spec F-07). Either the Sheet
   page becomes a view of the model's cells, or a sheet engine is built.
2. **Importers.** HYSYS / Aspen Plus / DWSIM options stay disabled: no
   importer exists in `src/ngdesign`.
3. **Auth in the browser.** The frontend sends no `Authorization` header, so
   with `STOMATO_API_TOKENS` set (deployed mode) every call except
   `/api/health` is 401. Local open mode is unaffected. Needs a sign-in or
   token-entry decision.
4. **Typed agent and catalogue responses.** `/api/thermo/models`,
   `/api/v1/catalogue/units`, the agent SSE events and transcripts are
   untyped in `openapi.json`; the frontend types them by hand in
   `api/client.ts`.
5. **Iso placement.** PUT `.../layout/iso/{key}` is not wired: placements are
   held in server memory with no GET to read them back.
6. **Design-spec brackets.** The outer loop evaluates the lower bound first; if
   the flowsheet is infeasible there (e.g. the slice's TEG contactor below its
   water floor when E-101 T_out = 300 K) the spec stops as "not met" with the
   unit's error, even when the target lies inside the bounds. This follows the
   P2-01 contract ("a spec aborted by a failed inner solve has
   converged=False"); a more forgiving bracket search is a solver decision.
7. **Async solve with progress.** Results uses the blocking POST `.../solve`;
   the job routes (`/jobs/solve`, SSE events) exist but are not used.
8. **Mock registry list.** `MOCK_META` in `client.ts` lists 4 thermo models
   and a subset of plugins (mock mode only). The new catalogue and thermo
   mocks are snapshots of the real endpoints.
