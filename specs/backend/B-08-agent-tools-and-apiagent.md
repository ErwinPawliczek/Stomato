# B-08: Engineering agent — Claude tool use over the project, streamed through `/api/agent`

- **Phase:** 4 (pulled forward: the hackathon showcase, docs/PLAN.md §4)
- **Depends on:** B-02 (`/api/solve`), B-03/B-04 (PFD/P&ID views), P0-03 (`ngdesign.pipeline`)
- **Packages you may edit:** `ngdesign.agent` (new modules; keep `session.py` as is), `ngdesign.api` (new `routes_agent.py`; `app.py` only to include the router and to inject the store), `ngdesign.api.routes_solve` (only to call the shared solve helper), `tests/agent/`, `tests/api/test_agent_route.py`, `scripts/agent_live.py` (new), `pyproject.toml` + `uv.lock` **only to add the `anthropic` dependency** (orchestrator applies `contract-change`), `openapi.json` + `frontend/src/api/schema.d.ts` (regenerated only)
- **Contract change:** yes — new API routes (openapi.json) and one new dependency
- **Benchmark delta expected:** none

## Goal
A process engineer types *"50 MMSCFD wet sour gas at 500 psia, 30 °C, sweeten with MDEA, dehydrate with
TEG, compress to 1200 psia"* and the system builds the flowsheet, solves it, and hands back PFD and P&ID —
every step visible as a tool call. The agent is Claude calling **typed tools over the in-process project**,
the same operations the HTTP routes perform. No tool runs anything the API cannot already do; the LLM
never sees secrets or the filesystem.

Today `AgentView` is a hard-coded sample and `ngdesign.agent.session` is an HTTP recipe runner (keep it).
This spec adds the real thing.

## Architecture (fixed)
```
POST /api/agent ──► api.routes_agent ──► agent.loop.run_turn(store, model, conversation, text)
                                              │
                      ┌───────────────────────┼─────────────────────────┐
                      ▼                       ▼                         ▼
               agent.tools (typed tools)  agent.model (ModelClient)  agent.engine (solve/render helpers)
                      │                       │
               ProjectStore protocol    AnthropicModel | ScriptedModel
               (api owns the state)     (tests never touch the network)
```
Layering (`.importlinter`): `api` imports `agent`; `agent` imports `pipeline`, `solver`, `contracts`,
`registry`; `agent` never imports `api`. The API injects the project store and the model into the loop.

## Files
- Create `src/ngdesign/agent/tools.py`
  - `ProjectStore` Protocol: `get() -> Project`, `put(Project) -> Project`.
  - `ToolSpec` dataclass: `name`, `description`, `input_schema` (JSON Schema, `additionalProperties:
    false`, every property in `required`, marked `strict: true` when sent to the API), `handler(store,
    engine, **input) -> dict`. `TOOLS: tuple[ToolSpec, ...]` is the registry; `tool_definitions()` renders
    the API `tools` list; `run_tool(name, input, store, engine) -> ToolOutcome(ok, result|error)`.
  - Tools (all return JSON-serialisable dicts; errors are returned, never raised, with `error` text):
    `get_project`, `list_unit_kinds` (registry kinds with `inlet_ports`, `outlet_ports`, and the params
    documented by each unit's `example_case()`), `list_components` (ids resolvable today: curated slate
    + the flowsheet's slate), `add_unit(tag, kind, params)`, `remove_unit(tag)`, `set_params(tag,
    params)` (merge), `add_feed(stream_id, target_unit, target_port, T_K, P_Pa, molar_flow_mol_s,
    composition)`, `connect(stream_id, source_unit, source_port, target_unit, target_port)`,
    `disconnect(stream_id)`, `set_thermo(name)`, `solve()` → `{converged, iterations, units: {tag:
    {duty_W, power_W, info}}, streams: {id: {T, P, molar_flow, vapor_fraction}}}`,
    `read_stream(stream_id)` (full `StreamState` incl. composition), `read_unit(tag)`,
    `read_variable(address)` (see addresses), `case_study(address, values, outputs)` → table rows,
    `render(view)` for `pfd` | `pid` → `{url, units, lines, instruments}` after
    `pipeline.build_pid`.
  - Every mutating tool validates through the pydantic contracts and stores the new `Project` with
    `store.put`; validation errors come back as the tool's `error` (the model fixes its own mistakes).
- Create `src/ngdesign/agent/addresses.py` — `resolve(address, solved) -> float`: `S-003.T`, `.P`,
  `.molar_flow`, `.mass_flow`, `.vapor_fraction`, `.x.CO2` (mole fraction), `K-101.duty_W`, `.power_W`,
  `.info.<key>`; `set_address(project, address, value)` for `K-101.params.<key>` and
  `S-001.feed.<T|P|molar_flow>` (case-study inputs). Unknown address → `ValueError` naming the nearest
  valid ones. (B-07 later generalises this into `ngdesign.variables`; keep the grammar identical.)
- Create `src/ngdesign/agent/engine.py` — `solve_project(project) -> SolvedFlowsheet` (registry thermo by
  `project.flowsheet.thermo`, `sequential_modular`, cached by project hash exactly as
  `api/routes_solve.py` does today — move that cache here and make the route call this; one solve path),
  `render_view(solved, layout, view) -> bytes` via `ngdesign.pipeline` + the registered renderers.
- Create `src/ngdesign/agent/model.py`
  - `ModelEvent` union: `TextDelta(text)`, `ToolUse(id, name, input)`, `TurnEnd(stop_reason,
    content_blocks, usage)`.
  - `ModelClient` Protocol: `stream_turn(system, tools, messages) -> Iterator[ModelEvent]`.
  - `AnthropicModel(ModelClient)` over the official `anthropic` Python SDK: `client.messages.stream(...)`
    with `model` from env `STOMATO_AGENT_MODEL` (default `claude-opus-5-5`), `max_tokens=16000`,
    `output_config={"effort": env STOMATO_AGENT_EFFORT or "medium"}`, **no** `thinking` parameter (adaptive
    is the default; never send `budget_tokens`), `tool_choice` left at auto (forced tool choice is
    rejected by current models), `cache_control: {"type": "ephemeral"}` on the system prompt and on the
    last tool definition. Parse tool inputs with `json.loads`, never string-match. Handle every
    `stop_reason`: `end_turn`, `tool_use`, `max_tokens` (emit an error event), `refusal` (emit an error
    event with `stop_details.category`). API key from `ANTHROPIC_API_KEY` only (SDK default resolution);
    never logged, never in a tool result.
  - `ScriptedModel(ModelClient)`: replays a list of scripted turns (text + tool calls) for tests and
    the mock mode; asserts the tool results it receives match what it expects.
- Create `src/ngdesign/agent/loop.py`
  - `Conversation` (pydantic): `id`, `messages` (the API `messages` array, assistant `content` appended
    **as returned**, tool results appended as ONE user message per round with every `tool_result`),
    `created_turns`.
  - `run_turn(store, engine, model, conversation, user_text) -> Iterator[AgentEvent]` where
    `AgentEvent` is the SSE payload below. Rules: all tool calls of one assistant message run in
    order and their results go back in one user message; a failing tool returns `is_error: true` with
    the error text; `project_changed` is emitted after any mutating tool; at most
    `MAX_TOOL_ROUNDS = 25` rounds per turn, then an `error` event; the system prompt is a module
    constant (`SYSTEM_PROMPT`) — units convention (SI in, degC/kPa(g)/kmol/h reported), always
    `list_unit_kinds` before adding an unknown kind, solve after topology changes, report what changed.
- Create `src/ngdesign/api/routes_agent.py`
  - `POST /api/agent` body `{message: str, conversation_id?: str}` → `text/event-stream`; one SSE
    `data:` line per event, JSON: `{"type":"text_delta","text"}`, `{"type":"tool_call","id","name","input"}`,
    `{"type":"tool_result","id","ok","summary","result"}` (`summary` ≤ 200 chars for the UI row;
    `result` the full dict), `{"type":"project_changed"}`, `{"type":"done","conversation_id",
    "stop_reason","usage":{"input_tokens","output_tokens","cache_read_input_tokens"}}`,
    `{"type":"error","message"}`. The stream always ends with `done` or `error`.
  - `GET /api/agent/{conversation_id}` → transcript (messages with tool calls/results);
    `DELETE /api/agent/{conversation_id}`; `GET /api/agent` → list of ids.
  - Conversations live in module state like the project does today (Phase 3 moves both). The model is
    built once per process: `ScriptedModel` when env `STOMATO_AGENT_MODE=scripted` (used by tests and
    `VITE_MOCK` demos), else `AnthropicModel`. A missing API key yields a clear `error` event, not a 500.
  - Register with one `app.include_router(agent_router)` line in `app.py`.
- Create `scripts/agent_live.py` — runs the showcase sentence against a live server with the real model
  and prints the event stream; skipped unless `ANTHROPIC_API_KEY` is set. Not a test.
- Tests
  - `tests/agent/test_tools.py`: every tool exercised without any LLM on the slice project: add/connect/
    set_params/remove round-trip the `Project`; invalid kind, duplicate tag, unknown port, bad composition
    each come back as `error` (never raise); `solve` on the slice converges; `read_variable` on
    `K-101.power_W` equals the solved result; `case_study("K-101.params.P_out", 5 values,
    ["K-101.power_W"])` is monotonic; `render("pfd")` returns a URL and counts.
  - `tests/agent/test_loop.py` with `ScriptedModel`: (1) a scripted session builds a 2-unit flowsheet
    (feed → separator → compressor) and solves it; event sequence asserted exactly; (2) two tool calls in
    one assistant message produce one user message with two `tool_result`s; (3) a failing tool yields
    `is_error` and the model's next turn sees it; (4) the 25-round cap produces an `error` event;
    (5) the showcase sentence with a scripted plan (MDEA absorber + TEG contactor + compressor on the
    sample sour gas) ends with a converged solve and both renders.
  - `tests/api/test_agent_route.py`: SSE framing (`data:` lines, JSON per event, ends with `done`),
    transcript round-trip, `DELETE`, missing-key error path, `STOMATO_AGENT_MODE=scripted`.
  - No test touches the network; `AnthropicModel` is covered by a unit test with the SDK client replaced
    by a stub that yields SDK-shaped stream events (`text`, `content_block_stop` with a `tool_use`
    block, final message), so the event mapping is tested.

## Method
Manual tool loop (own the loop; the SDK tool runner is not used so the model seam stays injectable).
Follow the current Anthropic Python SDK surface exactly: `anthropic.Anthropic()`, `client.messages.stream`,
`stream.get_final_message()`, `strict: true` tools with `additionalProperties: false`; no assistant
prefill; `output_config` for effort. Prompt caching: system prompt and tool list are byte-stable per
process (no timestamps). Transcripts are append-only. Cite the SDK docs section you implemented against
in the module docstring.

## Acceptance criteria
- [ ] `uv run pytest tests/agent tests/api/test_agent_route.py` green with no network
- [ ] Scripted showcase session (test 5) produces a converged 3-unit flowsheet and PFD + P&ID
- [ ] `openapi.json` regenerated; `cd frontend && npm run check:api && npm run typecheck` green
- [ ] `anthropic` added to `pyproject.toml` dependencies (not dev) and `uv.lock` updated; nothing else in those files changed
- [ ] `/api/solve` and the agent's `solve` share `agent.engine.solve_project` (one solve path, one cache)
- [ ] ruff, mypy, lint-imports (3 contracts kept), full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
The chat UI (F-08, parallel), authentication, persistence of conversations, multi-project, the Agent
SDK / Managed Agents, computer use, web search.
