# UI gaps: frontend features waiting on the backend (or the other way round)

Audit date: 2026-11-03, on `chem-engine` (merged at 6e2eada and later).
Method: every HTTP call in `frontend/src/api/client.ts` (the only module that
talks to the backend) was run against the real app with FastAPI's TestClient
and checked against the fields the views read. The frontend was then searched
for disabled, stubbed, mocked, placeholder, "planned" and hard-coded-sample
features.

## Endpoints the frontend calls (11)

| # | Client call | Method + path | Request | Fields the frontend reads | Backend status | Test |
|---|---|---|---|---|---|---|
| 1 | `api.getMeta` | GET `/api/meta` | none | `unit[]`, `thermo[]` | works | `tests/api/test_meta.py`, `test_app.py` |
| 2 | `api.getProject` | GET `/api/project` | none | `Project` (`name`, `flowsheet.units/streams/thermo`, `layout`) | works (deprecated alias of the `default` project) | `test_app.py` |
| 3 | `api.putProject` | PUT `/api/project` | `Project` | echoed `Project` | works; 422 on a contract violation | `test_app.py`, `test_validation.py` |
| 4 | `api.solve` | POST `/api/solve` | none | `converged`, `iterations`, `streams[id].{T,P,molar_flow,vapor_fraction}`, `units[tag].{duty_W,power_W,info}`; 501 means "solver not available" | works; 501 for an unregistered kind or thermo, 422 for an invalid project | `test_solve.py`, `test_solve_errors.py`, `test_frontend_contract.py` |
| 5 | `api.pfdSvg` | GET `/api/views/pfd.svg` | none | SVG with `viewBox` and `g[data-tag]` per unit | works | `test_views.py` |
| 6 | `api.pidSvg` | GET `/api/views/pid.svg` | none | SVG with `rect.equipment-bbox[data-tag][x][y]` per unit | **fixed**: was 500 for an unwired unit, now 422 | `test_pid_view.py`, `test_frontend_contract.py` |
| 7 | `api.plotSvg` | GET `/api/views/plot.svg` | none | SVG with `g[data-tag]` per unit | **fixed**: was 500 for an unwired unit, now 422 | `test_plot.py`, `test_frontend_contract.py` |
| 8 | `api.route` | POST `/api/route` | none | `PipingNetwork` (`lines`, `equipment`, `rack_elevation_mm`); 501/422 | **fixed**: was 500 for an unwired unit, now 422 | `test_plot.py`, `test_frontend_contract.py` |
| 9 | `api.place` | PUT `/api/project/layout/{pfd\|pid}/{tag}` | `XY {x, y}` | `Layout {pfd, pid, plot}` | works | `test_app.py`, `test_pid_view.py`, `test_frontend_contract.py` |
| 10 | `api.placePlot` | PUT `/api/project/layout/plot/{tag}` | `Vec3 {x, y, z}` | `Layout` | works (422 without `z`) | `test_plot.py`, `test_frontend_contract.py` |
| 11 | `api.agent.send` | POST `/api/agent` (SSE) | `{message, conversation_id?}` | `data:` frames: `text_delta`, `tool_call`, `tool_result`, `project_changed`, `done{conversation_id, stop_reason, usage}`, `error{message}`; 404 for an unknown conversation | works | `test_agent_route.py` |

The one backend defect found: a unit added from the Flowsheet palette has no
streams wired yet. It solves, and the PFD draws it, but the P&ID chain's sizer
or builder raised `ValueError`. That made the P&ID view, plot plan, re-route
and isometrics an unhandled **500**. `pipeline.build_pid` now raises
`UndrawableProjectError` and the app maps it to **422** with the reason
("unit E-901 has no connected streams to size from"). This covers the legacy
routes and the `/api/projects/{id}/...` routes.

## Frontend features waiting on the backend

| Feature (file) | State in the UI | Endpoint or contract it needs | Backend status |
|---|---|---|---|
| New project, project list (`views/HomeView.tsx`) | "New project" button disabled ("Needs a multi-project endpoint"); one hard-wired project card | `/api/projects` CRUD and project-scoped routes | **In progress elsewhere** (`~/stomato-projects`). Not touched here. |
| Isometrics sub-tab (`views/DrawingsView.tsx`) | `<Placeholder>`: "Isometrics arrives in layer L6" | GET `/api/views/iso`, `/api/views/iso/{line}.svg`, `/api/views/iso/{line}.json`, PUT `/api/project/layout/iso/{key}` | **Exists** (tested in `test_iso_view.py`); frontend not wired |
| Import Aspen HYSYS / Aspen Plus / DWSIM (`views/HomeView.tsx`) | Disabled options marked "planned" | An importer endpoint (e.g. POST `/api/import/{format}` returning `Project`) | **Missing**: no importer in `src/ngdesign` |
| Sheet page (`views/SheetView.tsx`) | Plain grid; values in memory only; "formulas and saving come with the sheet engine (F-07)" | Sheet engine: formula evaluation over model variables and persistence | **Partial**: GET `/api/export/sheet?format=csv\|html` exports; no evaluate or save endpoint |
| Equipment page (`equipmentCatalog.ts`) | Ports, params, descriptions and sizers per kind are hand-copied from the plugin sources; only names come from `/api/meta` | Per-kind metadata (ports, params with units and defaults, sizer) | **Missing**: `/api/meta` returns names only |
| Unit palette, canvas (`unitCatalogue.ts`, `unitPalette.ts`) | Name, family, P&ID symbol and summary for all 84 catalogue units are a generated frontend mirror of `data/unit_models/*.yaml`, guarded by a drift test; `/api/meta` decides `available` | Unit-catalogue endpoint (e.g. GET `/api/units/catalogue` serving the YAML rows) | **Missing**: no route exposes `data/unit_models` |
| Add-unit defaults (`unitDefaults.ts`) | Default params per kind hard-coded "until /api/meta drops param defaults" | Per-kind defaults (each plugin's `example_case()` params) | **Missing** (same endpoint as the row above) |
| Agent event types (`api/client.ts` `AgentEvent`) | Typed by hand because `schema.d.ts` has no SSE event schema | SSE event schema in `openapi.json` | **Works at runtime**; `POST /api/agent` declares no response schema |
| Agent history (`views/AgentView.tsx`) | Conversation lost on reload; no list, reopen or delete | GET `/api/agent`, GET/DELETE `/api/agent/{conversation_id}` | **Exists**; frontend not wired |
| Async solve with progress (`views/ResultsView.tsx`) | Blocking POST `/api/solve` with a "Solving…" label | POST `/api/projects/{id}/jobs/solve`, GET `/api/jobs/{id}`, GET `/api/jobs/{id}/events` (SSE) | **Exists** (project-scoped only, so it depends on multi-project) |
| Case study | No UI | POST `/api/study` | **Exists**; no UI |
| Sheet export / datasheet download | No UI | GET `/api/export/sheet` | **Exists**; no UI |
| Reset to sample | No UI | POST `/api/project/reset` | **Exists**; no UI |
| Thermo recommendation | No UI | GET `/api/thermo/recommend` | **Exists**; no UI |
| Mock mode (`api/client.ts` `MOCK_META`, `mocks/*.json`) | `VITE_MOCK=1` and tests use canned data; `MOCK_META` lists 4 thermo models and 16 unit kinds, the live registry has about 160 and many more | Nothing (mock-only) | Not a backend gap; the mock list is stale |

## Frontend-side mismatches

The backend contract is correct here and the frontend uses it wrongly or not
at all. These need a frontend-only change (AGENTS.md: never change both sides
in one PR).

1. **Thermo selector offers unusable models.** `FlowsheetView` fills the
   selector from `/api/meta` `thermo` (every registered name, about 160).
   GET `/api/thermo/models` marks `experimental` rows `selectable: false` with
   a `refusal_reason`. Picking one (e.g. `flory_huggins`, `hf_hexamer`) saves
   fine and then every solve and view returns 422. Use `/api/thermo/models`.
2. **Results ignore solve failures.** `ResultsView` shows only
   `converged`/`iterations`. A failed unit returns 200 with
   `status: "failed"` and per-unit `errors[] {tag, kind, error_type, message,
   stage, upstream}`. The UI says "Did not converge" with no reason.
   `history` and `design_spec_results` are unused too.
3. **Stale agent conversation never recovers.** POST `/api/agent` with an
   unknown `conversation_id` is 404 ("start a new conversation").
   `AgentView` keeps the stale id, so every later send fails until reload.
   It should drop the id on a 404 `ApiError` and retry or start fresh.
4. **No auth header.** `http()`/`httpText()`/`agent.send` send no
   `Authorization`. With `STOMATO_API_TOKENS` set (deployed mode), every call
   except `/api/health` is 401. Local open mode is unaffected.
5. **Unwired-unit drawing errors.** Since the 422 fix, the P&ID and plot views
   receive `{"detail": "unit E-901 has no connected streams to size from"}`.
   They show the raw `ApiError` text. A friendlier "wire E-901 first" message
   is a frontend nicety, not a contract gap.
6. **Placing unsaved units only works on the legacy route.** The Flowsheet
   canvas calls `api.place("pfd", tag, …)` for units added since the last
   save. The legacy PUT `/api/project/layout/pfd/{tag}` accepts any tag. Its
   project-scoped twin returns 409 for a tag not in the stored project. When
   the frontend moves to `/api/projects/{id}` (multi-project, in progress
   elsewhere), it must save the unit before placing it.
