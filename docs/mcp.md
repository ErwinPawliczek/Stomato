# stomato-mcp: Stomato over the Model Context Protocol

`stomato-mcp` lets any MCP client drive Stomato's process simulator: Claude Desktop, Claude Code, Cursor, or
your own agent. It serves the same tools as the in-app agent and `POST /api/v1/projects/{id}/tools/{name}`.
They are one implementation (`ngdesign.agent.tools` → `ngdesign.agent.service`), so the three surfaces can't
drift. Every edit is an undoable change in the same database the web app reads. If the Stomato UI is open on
the project, it shows each edit live, attributed to `mcp:<client name>`.

Design: [agentic-layer.md](agentic-layer.md).

## Install and run

```bash
uv sync                          # installs the `stomato-mcp` console script
uv run stomato-mcp               # stdio (default)
uv run stomato-mcp --transport http --port 8765    # streamable HTTP at http://127.0.0.1:8765/mcp
```

| Option / env | Meaning |
|---|---|
| `--transport stdio\|http` | stdio (one client per process) or streamable HTTP |
| `--host`, `--port` | HTTP bind address (default `127.0.0.1:8765`; localhost DNS-rebinding protection is on) |
| `--project <id>` / `STOMATO_MCP_PROJECT` | project to start on (default: your `default` project, created from the sample slice) |
| `--owner <name>` / `STOMATO_MCP_OWNER` | owner for stdio sessions (default `local`, the web app's open-mode owner) |
| `STOMATO_DATABASE_URL` | the store, same as the API (default `sqlite:///./stomato.db` relative to the working directory) |
| `STOMATO_API_TOKENS` | HTTP only: `token:owner,…`; each request then needs `Authorization: Bearer <token>` |

To see MCP edits live in the UI, point `STOMATO_DATABASE_URL` (or the working directory) at the same database
as the API server.

## Claude Desktop

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "stomato": {
      "command": "uv",
      "args": ["--directory", "/path/to/stomato", "run", "stomato-mcp"],
      "env": { "STOMATO_DATABASE_URL": "sqlite:////path/to/stomato/stomato.db" }
    }
  }
}
```

## Cursor

`.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` globally):

```json
{
  "mcpServers": {
    "stomato": {
      "command": "uv",
      "args": ["--directory", "/path/to/stomato", "run", "stomato-mcp"],
      "env": { "STOMATO_DATABASE_URL": "sqlite:////path/to/stomato/stomato.db" }
    }
  }
}
```

Or connect to a running HTTP server:

```json
{ "mcpServers": { "stomato": { "url": "http://127.0.0.1:8765/mcp" } } }
```

## Claude Code

```bash
claude mcp add stomato -- uv --directory /path/to/stomato run stomato-mcp
```

## Tools

The agent tools, with the same names, descriptions and JSON schemas as `GET /api/v1/tools`. Each one also takes an
optional `project_id`, which defaults to the current project.

| Group | Tools |
|---|---|
| session | `list_projects`, `create_project` (blank or `template`, becomes current), `open_project` |
| catalogue | `list_catalogue`, `describe_unit_kind`, `list_unit_kinds`, `list_components`, `recommend_thermo` |
| build | `place_unit` (`position {x,y}` or hex `grid {q,r}`), `move_unit`, `configure_unit`, `remove_unit`, `add_feed`, `connect`, `update_stream`, `disconnect`, `set_thermo`, `set_components`, `add_unit`, `set_params` |
| variables | `list_cells`, `set_cell` (value + unit, e.g. `25` `degC`, `65` `bar`), `add_design_spec`, `remove_design_spec` |
| solve & read | `solve`, `read_results` (optionally converted to a unit), `read_stream`, `read_unit`, `read_variable`, `case_study`, `render` |
| provenance | `explain_value`: each method with its reference, and the inputs and data with their sources |
| history | `undo`, `redo`, `list_changes` |

A mutating tool returns its result plus `change: {seq, actor, summary, diff, lines}`. A failed call returns
`isError: true` with `{error, code}`, where the error names the nearest valid inputs so the model can correct
itself.

The current project is remembered per owner, so `open_project` and `create_project` switch it for that owner's
later calls. Pass `project_id` explicitly when several clients share one HTTP server and owner.

## Resources

| URI | Content |
|---|---|
| `stomato://projects` | your projects |
| `stomato://catalogue/units` | unit kinds with family and ports |
| `stomato://projects/{project_id}` | the project: identity, version, body |
| `stomato://projects/{project_id}/flowsheet` | units, streams, thermo, components, design specs |
| `stomato://projects/{project_id}/results` | solved results summary (solves if needed) |
| `stomato://projects/{project_id}/trace` | the calculation provenance graph |
| `stomato://projects/{project_id}/changes` | change history with actors and diffs |

## Example session

```text
list_catalogue {"section": "units"}
place_unit {"kind": "cooler", "tag": "E-201", "params": {"T_out": 313.15, "dP": 20000},
            "position": null, "grid": {"q": 6, "r": 0}, "view": null}
add_feed {"stream_id": "S-020", "target_unit": "E-201", "target_port": "inlet", "T_K": 330.0,
          "P_Pa": 3.0e6, "molar_flow_mol_s": 50.0, "composition": {"C1": 0.9, "C2": 0.1}, "service": "PG"}
connect {"stream_id": "S-021", "source_unit": "E-201", "source_port": "outlet",
         "target_unit": null, "target_port": null, "service": "PG"}
set_cell {"address": "K-101.params.P_out", "value": 65, "unit": "bar"}
read_results {"address": "S-003.T", "unit": "degC"}
explain_value {"address": "S-003.T"}
undo {}
```

## Tests

`tests/mcp/test_server.py` drives the server with the official MCP `Client` in three ways: in memory (every tool
surface and resource), over stdio (`python -m ngdesign.mcp` as a subprocess) and over streamable HTTP (uvicorn on
loopback, including the bearer check).
