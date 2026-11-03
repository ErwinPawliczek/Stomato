# The agentic layer

Status: design (written before the code; kept in sync with it).

Goal: agents can drive Stomato's chemical process simulation as well as the web app can.
There are three ways in: a **versioned public REST API**, an **MCP server** (`stomato-mcp`)
and the **in-app agent** (chat panel). All three run the **same operations** through
**one tool layer**. Every edit any of them makes is a recorded, undoable project change
that the UI sees live.

```
                ┌───────────── web UI (React) ─────────────┐
                │ Flowsheet / Results / … tabs  Agent panel │
                └──────┬──────────────────────────┬────────┘
     REST /api/v1 (+legacy /api)            SSE /api/v1/.../agent
                       │                          │
 MCP client ─ stomato-mcp (stdio | streamable HTTP)│
        │              │                          │
        ▼              ▼                          ▼
   ngdesign.mcp   ngdesign.api.v1          ngdesign.agent.loop
        │              │                          │   (AnthropicModel | ScriptedModel)
        └──────────────┴────────────┬─────────────┘
                                    ▼
                 ngdesign.agent.tools   (TOOLS: name, JSON schema, handler, mutates)
                                    ▼
                 ngdesign.agent.service (ProjectService: typed operations, OpError)
                       │                       │
     ngdesign.agent.engine (solve/trace)   ngdesign.variables / ngdesign.uom
                       │
                 ProjectStore + ChangeLog  (ngdesign.store.DbProjectStore, SQL)
```

## 1. What exists (before this work)

| Piece | Where | Notes |
|---|---|---|
| Tool registry (17 tools, strict JSON schemas) | `agent/tools.py` | handlers over a `ProjectStore` (`get`/`put`) + `Engine` |
| Conversation loop | `agent/loop.py` | model/tool rounds, SSE-ready events, `MAX_TOOL_ROUNDS` |
| Model seam | `agent/model.py` | `AnthropicModel` (key from env, never logged), `ScriptedModel`, SDK stubs |
| Scripted HTTP session | `agent/session.py` | deterministic L8 recipe over a `Transport` |
| Solve/trace/render | `agent/engine.py` | one solve path and cache shared by the routes and the tools |
| Routes | `api/routes_*.py` | project-scoped `/api/projects/{id}/…` plus deprecated unscoped aliases; `/api/agent` SSE; jobs; study; trace; views; export |
| Store | `store/` | `DbProjectStore` (versioned JSON body), conversations |
| Frontend | `frontend/src/views/AgentView.tsx` | chat, collapsible tool rows, `project_changed` → refresh signal |

Gaps this design closes:

* No versioned or documented public API. Errors are FastAPI's `{"detail": …}` with mixed shapes, and the
  tool operations exist only inside `agent/tools.py`.
* No undo and no change history. An agent edit is a silent `put`.
* No MCP server.
* The UI only learns about changes from its own agent stream. Edits from MCP or another client are invisible
  until a reload.
* Bug: `engine.rebuild_flowsheet` rebuilt `Flowsheet` from five fields and dropped `design_specs`,
  `solver_options` and `reactions` on every tool edit. Fixed by revalidating a full model copy.

## 2. One operation layer: `ProjectService`

`ngdesign.agent.service.ProjectService(store, engine, actor)` holds the typed operations. Every surface calls
them, and nothing else mutates a project:

| Group | Operations |
|---|---|
| catalogue | `catalogue()` (unit kinds from the U-00 catalogue with ports, param schema, rigour levels; components; thermo packages) |
| thermo | `set_thermo(package)`, `set_components(ids)`, `recommend_thermo()` |
| units | `place_unit(kind, tag?, params, position?, grid?)`, `move_unit(tag, x, y, view)`, `configure_unit(tag, params, replace)`, `delete_unit(tag)`, `rename_unit` (not in v1) |
| streams | `add_feed(…)`, `connect(…)`, `update_stream(id, service?, feed?)`, `delete_stream(id)` |
| cells | `cells()` (every writable address with its value, SI unit and kind), `set_cell(address, value, unit?)` |
| design specs | `add_design_spec(spec)`, `delete_design_spec(id)` |
| solve / results | `solve()`, `results()`, `read(address, unit?)`, `stream_result`, `unit_result` |
| provenance | `explain(address)`: the trace subgraph of one value, plus a plain-text derivation |
| history | `undo()`, `redo()`, `changes(after)` |

Rules:

* **Errors are typed.** Each `OpError(code, message, status, details)` carries a stable `code`, e.g.
  `unknown_unit`, `unknown_kind`, `bad_port`, `port_in_use`, `invalid_project`, `unit_mismatch`,
  `nothing_to_undo`, `conflict`. The message always says how to fix the input (nearest valid names). REST maps
  `status`; tools return `{"error": message, "code": code}` to the model.
* **One commit path.** A mutating operation builds the new `Project` through the pydantic contracts and calls
  `store.commit(project, op=…, actor=…, summary=…, args=…)`. The returned `ChangeRecord` carries the structured
  diff. Failed validation never writes.
* **Units at the edge.** `set_cell` / `read` accept `unit` strings parsed by `ngdesign.uom`. Values are SI
  internally. The expected dimension is known for feed fields (T, P, molar_flow, composition). For unit
  params it comes from the catalogue's own param description (`'outlet pressure, Pa'` gives Pa). A param with
  no declared unit is treated as SI and gets a dimensionless check only when the caller gives no unit.
  Nothing is invented.
* **Grid positions.** The flowsheet canvas is a flat-top hex lattice (`frontend/src/hexGrid.ts`, circumradius
  40 layout units). `place_unit(…, grid={q, r})` maps to the cell centre with the same formula, so an agent
  can say "next to V-101" in grid terms. `position={x, y}` places freely. With neither, the unit goes to the
  first free cell right of the existing units.

## 3. Change log, undo, live UI

`ChangeRow` (store schema v3): `project_id, seq, kind (edit|undo|redo), op, actor, summary, args_json,
before_json, after_json, state (applied|undone|dropped), target_seq, created_at`.

* `DbProjectStore.commit(...)` writes the body and the change row in **one transaction**. The plain `put`
  (legacy PUT, layout drags) also records a change (`op="put"`, `actor="api"`), so the log is complete and
  undo is consistent whichever client edited. A `put` that changes nothing records nothing.
* `undo()` takes the latest `applied` edit/redo-target, requires `current body == its after` (else `conflict`),
  restores `before`, marks it `undone` and appends an `undo` row. `redo()` re-applies the most recent `undone`
  change. A new edit marks every `undone` row `dropped`, as a linear history should.
* The diff (`agent/diff.py`, pure) is computed from before/after: units added/removed/changed (param-level
  `from → to`), streams added/removed/changed, thermo, components, design specs, layout moves.
* **Live UI.** `GET /api/v1/projects/{id}/changes?after=seq` lists changes, and
  `GET /api/v1/projects/{id}/changes/stream` is an SSE stream of the same records (it polls the DB, so changes
  from another process, such as the MCP server on the same database, appear too). The UI subscribes, raises
  its existing `notifyProjectChanged()` signal and shows the change in the Agent panel's history with
  Undo/Redo.

Actors: `api` (REST), `ui` (sent by the web client as `X-Stomato-Actor: ui`), `agent:<conversation>` (in-app),
`mcp` (MCP server, with the client name when it is known).

## 4. Public REST API v1

Prefix `/api/v1`, tag-grouped in OpenAPI, every request model with `examples`. The legacy routes stay
unchanged for the current UI.

Error envelope (every 4xx/5xx under `/api/v1`):
```json
{"error": {"code": "unknown_unit", "message": "unknown unit 'V-9'; have ['K-101', 'V-101']", "details": {}}}
```
Validation errors use `code: "validation_error"` with `details.errors` (pydantic's list).

| Area | Endpoints |
|---|---|
| meta | `GET /api/v1` (version, links), `GET /api/v1/tools` (the tool catalogue, the same list MCP serves) |
| catalogue | `GET /catalogue/units`, `GET /catalogue/units/{kind}`, `GET /catalogue/components`, `GET /catalogue/thermo` |
| projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, `GET /projects/{id}/flowsheet` |
| thermo | `GET/PUT /projects/{id}/thermo` (`package`, `components`), `GET /projects/{id}/thermo/recommend` |
| units | `GET/POST /projects/{id}/units`, `GET/PATCH/DELETE /projects/{id}/units/{tag}`, `PUT /projects/{id}/units/{tag}/position` |
| streams | `GET/POST /projects/{id}/streams`, `GET/PATCH/DELETE /projects/{id}/streams/{sid}` |
| cells | `GET /projects/{id}/cells`, `GET/PUT /projects/{id}/cells/{address}` (`{value, unit?}`) |
| design specs | `GET/POST /projects/{id}/design-specs`, `DELETE /projects/{id}/design-specs/{spec_id}` |
| solve | `POST /projects/{id}/solve` (sync, summary + diagnostics), `POST /projects/{id}/solve/jobs` (202), `GET /jobs/{job_id}`, `GET /jobs/{job_id}/events` (SSE) |
| results | `GET /projects/{id}/results`, `GET /projects/{id}/results/streams/{sid}`, `GET /projects/{id}/results/units/{tag}`, `GET /projects/{id}/results/values/{address}?unit=` |
| provenance | `GET /projects/{id}/trace`, `GET /projects/{id}/trace/explain?address=`, `GET /projects/{id}/trace/audit` |
| exports | `GET /projects/{id}/exports/project.json`, `/exports/sheet.csv`, `/exports/sheet.html`, `/exports/pfd.svg`, `/exports/pid.svg` |
| history | `GET /projects/{id}/changes`, `GET /projects/{id}/changes/stream`, `POST /projects/{id}/undo`, `POST /projects/{id}/redo` |
| tools | `POST /projects/{id}/tools/{name}`: run any agent tool by name (the same handler MCP and the in-app agent call) |
| agent | `POST /projects/{id}/agent` (SSE, same frames as before plus `change` on mutating results) |

Auth is unchanged (bearer tokens via `STOMATO_API_TOKENS`; open in local dev). Owner checks come from
`deps.project_store`.

## 5. Tools (single source of truth)

`agent/tools.py` keeps the `TOOLS` tuple (strict JSON schemas, fixed order for prompt caching). The B-08 tools
keep their names and schemas. Their handlers now delegate to `ProjectService`. New tools:

`list_catalogue`, `place_unit`, `move_unit`, `configure_unit`, `update_stream`, `list_cells`, `set_cell`,
`add_design_spec`, `remove_design_spec`, `read_results`, `explain_value`, `undo`, `redo`, `list_changes`.

A tool result of a mutating tool includes `change: {seq, summary, diff}`. The loop forwards it in the
`tool_result` SSE event, and the UI renders it under the tool row.

Surfaces:
* in-app agent: `tool_definitions()` goes to the Anthropic API;
* MCP: `list_tools` serves the same names, descriptions and schemas, plus an optional `project_id` argument
  (non-strict) and three session tools: `list_projects`, `create_project`, `open_project`;
* REST: `GET /api/v1/tools`, `POST /api/v1/projects/{id}/tools/{name}`.

## 6. MCP server `stomato-mcp`

Package `ngdesign.mcp` (official `mcp` Python SDK, low-level `Server` so the tool schemas are passed through
verbatim). Console entry point `stomato-mcp`:

```
stomato-mcp                      # stdio (Claude Desktop, Cursor, Claude Code)
stomato-mcp --transport http --port 8765   # streamable HTTP at /mcp
```

* Project selection: `project_id` argument → the session's `open_project` choice → `STOMATO_MCP_PROJECT`
  → the owner's `default` project (created from the sample slice like the legacy routes).
* Owner: `STOMATO_MCP_OWNER` (default `local`, the open-mode owner the web app uses). Over HTTP with
  `STOMATO_API_TOKENS` set, the bearer token maps to the owner exactly as in the REST API.
* Database: `STOMATO_DATABASE_URL`, the same store as the web app. Changes made through MCP appear live in the
  UI's change stream.
* Resources: `stomato://projects`, plus the templates `stomato://projects/{id}`, `…/flowsheet`, `…/results`,
  `…/trace`, `…/changes` (JSON).
* Tool errors return `isError: true` with the operation's message, so the client model can fix its call.

## 7. In-app agent

`POST /api/v1/projects/{id}/agent` runs `agent.loop.run_conversation` with the same `TOOLS`. The actor is
`agent:<conversation_id>`. The model is `AnthropicModel` with `ANTHROPIC_API_KEY` taken from the environment
only (never logged or echoed; a missing key is a clear SSE error), or `ScriptedModel` when
`STOMATO_AGENT_MODE=scripted` (deterministic, no network; every test uses it).

UI: the Agent panel shows each tool call (input, result) and, for mutating calls, the diff it made. A
History strip lists recent changes from any actor with Undo/Redo, and the project-changed signal fires on
every change from the stream.

## 8. Layering

`.importlinter` gains `ngdesign.mcp` next to `ngdesign.cli` at the top. `ngdesign.mcp` imports `store`,
`agent` and `api.auth` (token parsing). The tool layer stays in `ngdesign.agent` (below `store`): it reaches
the change log only through the structural `ProjectStore`/`ChangeLog` protocols, never by importing the store.

## 9. Testing

* `tests/store/test_changes.py`: commit/undo/redo/drop semantics and the conflict guard.
* `tests/agent/test_service.py`, `test_diff.py`, plus the existing B-08 tool tests unchanged.
* `tests/api/test_v1_*.py`: at least one success and one error case per endpoint, envelope shape, OpenAPI
  examples present.
* `tests/mcp/`: an MCP `Client` against the in-memory server (every tool and resource), a stdio subprocess
  round-trip and a streamable-HTTP round-trip.
* Frontend: Agent panel diff rendering, history undo, change-stream refresh (vitest, mocked client).
* No test touches the network. The scripted model drives every agent conversation.
