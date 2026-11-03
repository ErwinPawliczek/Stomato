"""The Stomato MCP server (docs/agentic-layer.md section 6, docs/mcp.md).

Built on the official MCP Python SDK's low-level :class:`mcp.server.Server` so
the agent tools' JSON schemas pass through verbatim: ``list_tools`` serves
exactly :data:`ngdesign.agent.tools.TOOLS` (plus an optional ``project_id``
argument) and three session tools (``list_projects``, ``create_project``,
``open_project``); ``call_tool`` runs :func:`ngdesign.agent.tools.run_tool` —
the handler the in-app agent and ``POST /api/v1/projects/{id}/tools/{name}``
run. Every edit is a logged, undoable change attributed to ``mcp`` (with the
client's name when it sends one) in the same database the web app reads, so the
UI's change stream shows it live.

Transports: stdio (default; Claude Desktop, Cursor, Claude Code) and streamable
HTTP (``--transport http``, path ``/mcp``). Over HTTP with
``STOMATO_API_TOKENS`` set, a bearer token is required and maps to the owner
exactly like the REST API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import mcp.types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types.jsonrpc import INVALID_PARAMS

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.service import ProjectService, change_payload, unit_catalogue
from ngdesign.agent.tools import TOOLS, TOOLS_BY_NAME, ToolOutcome, run_tool
from ngdesign.api import auth
from ngdesign.api.deps import default_project_store, project_store
from ngdesign.api.routes_projects import ProjectCreate, _info, _source
from ngdesign.store import (
    DbProjectStore,
    ProjectExists,
    ProjectForbidden,
    ProjectNotFound,
    create_project,
    init_db,
    list_projects,
)

SERVER_NAME = "stomato"

#: Environment: the owner stdio sessions act as, and the project they start on.
OWNER_ENV = "STOMATO_MCP_OWNER"
PROJECT_ENV = "STOMATO_MCP_PROJECT"

INSTRUCTIONS = """\
Stomato is a steady-state chemical process simulator. These tools edit and solve \
one project at a time (the current project: open_project to switch, or pass \
project_id to any tool). Units are SI unless a tool takes a unit string. Typical \
loop: list_catalogue / describe_unit_kind -> place_unit -> connect / add_feed -> \
set_cell -> solve -> read_results -> explain_value. Every edit is an undoable \
change that the Stomato web app shows live; undo reverts the latest one. Tool \
errors say what was wrong and the nearest valid inputs."""

_SESSION_TOOLS: tuple[types.Tool, ...] = (
    types.Tool(
        name="list_projects",
        description="The projects you own: id, name, version, template, last update.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=types.ToolAnnotations(read_only_hint=True),
    ),
    types.Tool(
        name="create_project",
        description="Create a project (blank, or from a template such as 'slice') and make it current.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "template": {"type": ["string", "null"], "description": "Template id; null: blank"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="open_project",
        description="Make a project current for this session (tools without project_id use it).",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
    ),
)

_DESTRUCTIVE = {"remove_unit", "disconnect"}

_URI = re.compile(r"^stomato://projects/(?P<id>[^/]+)(?:/(?P<part>flowsheet|results|trace|changes))?$")


def _tool(spec: Any) -> types.Tool:
    """One agent tool as an MCP tool: same name/description/schema, plus project_id."""
    schema = json.loads(json.dumps(spec.input_schema))
    schema.setdefault("properties", {})["project_id"] = {
        "type": "string",
        "description": "Project to act on; omitted: the session's current project",
    }
    return types.Tool(
        name=spec.name,
        description=spec.description,
        input_schema=schema,
        annotations=types.ToolAnnotations(
            read_only_hint=not spec.mutates,
            destructive_hint=spec.name in _DESTRUCTIVE if spec.mutates else None,
        ),
    )


def _json(payload: Any, *, error: bool = False) -> types.CallToolResult:
    text = json.dumps(payload, default=str)
    structured = payload if isinstance(payload, dict) else {"value": payload}
    return types.CallToolResult(
        content=[types.TextContent(text=text)], structured_content=structured, is_error=error
    )


class StomatoMCP:
    """Session state and handlers; :meth:`server` builds the SDK server."""

    def __init__(self, *, owner: str | None = None, project_id: str | None = None) -> None:
        self.default_owner = owner or os.environ.get(OWNER_ENV) or auth.ANONYMOUS_OWNER
        self.default_project = project_id or os.environ.get(PROJECT_ENV)
        # The current project per owner. Not per connection: on the 2026-07-28
        # protocol every request is self-contained (no session object survives
        # between calls), and a stdio server serves exactly one client anyway.
        self._current: dict[str, str] = {}

    # -- identity --------------------------------------------------------------

    def owner(self, ctx: ServerRequestContext[Any, Any] | None) -> str:
        """The owner: the bearer token's (HTTP with tokens configured), else the default."""
        request = getattr(ctx, "request", None) if ctx is not None else None
        state = auth.auth_state()
        if request is None or state.tokens is None:
            return self.default_owner
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        owner = state.tokens.get(token.strip()) if scheme.lower() == "bearer" else None
        if owner is None:
            raise PermissionError("a valid 'Authorization: Bearer <token>' is required")
        return owner

    @staticmethod
    def actor(ctx: ServerRequestContext[Any, Any] | None) -> str:
        client = None
        try:
            params = ctx.session.client_params if ctx is not None else None
            client = params.client_info.name if params is not None else None
        except AttributeError:
            client = None
        if client:
            safe = re.sub(r"[^A-Za-z0-9_.\-]", "-", str(client))[:40]
            return f"mcp:{safe}"
        return "mcp"

    def store(self, ctx: ServerRequestContext[Any, Any] | None, project_id: str | None) -> DbProjectStore:
        owner = self.owner(ctx)
        chosen = project_id or self._current.get(owner) or self.default_project
        if chosen is None:
            return default_project_store(owner)
        return project_store(chosen, owner)

    # -- tools -------------------------------------------------------------------

    def tools(self) -> list[types.Tool]:
        return [*(_tool(spec) for spec in TOOLS), *_SESSION_TOOLS]

    def call(
        self, ctx: ServerRequestContext[Any, Any] | None, name: str, args: dict[str, Any]
    ) -> types.CallToolResult:
        """Run one tool synchronously (the async handler runs this in a worker thread)."""
        try:
            if name == "list_projects":
                return _json(
                    {
                        "projects": [
                            {
                                "id": r.id,
                                "name": r.name,
                                "version": r.version,
                                "template": r.template,
                                "updated_at": r.updated_at.isoformat(),
                            }
                            for r in list_projects(self.owner(ctx))
                        ]
                    }
                )
            if name == "create_project":
                owner = self.owner(ctx)
                body = ProjectCreate(name=args["name"], template=args.get("template"))
                project, template_id = _source(body, owner)
                row = create_project(name=body.name, owner=owner, project=project, template=template_id)
                self._current[owner] = row.id
                return _json({"created": row.id, "name": row.name, "current": True})
            if name == "open_project":
                owner = self.owner(ctx)
                store = project_store(str(args["project_id"]), owner)
                self._current[owner] = store.project_id
                return _json({"current": store.project_id, "name": store.row().name})
            if name not in TOOLS_BY_NAME:
                return _json({"error": f"unknown tool {name!r}", "code": "unknown_tool"}, error=True)
            tool_args = dict(args)
            project_id = tool_args.pop("project_id", None)
            store = self.store(ctx, project_id)
            outcome: ToolOutcome = run_tool(name, tool_args, store, DEFAULT_ENGINE, actor=self.actor(ctx))
            return _json(outcome.payload(), error=not outcome.ok)
        except (ProjectNotFound, ProjectForbidden, ProjectExists, PermissionError) as exc:
            return _json({"error": str(exc), "code": type(exc).__name__}, error=True)
        except Exception as exc:  # noqa: BLE001 — HTTPException from shared helpers, bad args
            detail = getattr(exc, "detail", None) or str(exc)
            return _json({"error": str(detail), "code": type(exc).__name__}, error=True)

    # -- resources -------------------------------------------------------------------

    def resources(self, ctx: ServerRequestContext[Any, Any] | None) -> list[types.Resource]:
        out = [
            types.Resource(
                uri="stomato://projects",
                name="projects",
                description="Your projects (id, name, version)",
                mime_type="application/json",
            ),
            types.Resource(
                uri="stomato://catalogue/units",
                name="unit catalogue",
                description="Every unit kind with family and ports",
                mime_type="application/json",
            ),
        ]
        for row in list_projects(self.owner(ctx)):
            out.append(
                types.Resource(
                    uri=f"stomato://projects/{row.id}",
                    name=f"project {row.name}",
                    description=f"Project {row.name!r} (version {row.version})",
                    mime_type="application/json",
                )
            )
        return out

    @staticmethod
    def templates() -> list[types.ResourceTemplate]:
        parts = {
            "": "The project: identity, version and full body",
            "/flowsheet": "Units, streams, thermo, components, design specs",
            "/results": "Solved results summary (solves if needed)",
            "/trace": "The calculation provenance graph of the solved project",
            "/changes": "The change history with actors and structured diffs",
        }
        return [
            types.ResourceTemplate(
                uri_template=f"stomato://projects/{{project_id}}{suffix}",
                name=f"project{suffix.replace('/', ' ')}".strip(),
                description=desc,
                mime_type="application/json",
            )
            for suffix, desc in parts.items()
        ]

    def read(self, ctx: ServerRequestContext[Any, Any] | None, uri: str) -> str:
        if uri == "stomato://projects":
            rows = list_projects(self.owner(ctx))
            return json.dumps(
                {"projects": [{"id": r.id, "name": r.name, "version": r.version} for r in rows]}
            )
        if uri == "stomato://catalogue/units":
            return json.dumps({"units": unit_catalogue()})
        match = _URI.match(uri)
        if match is None:
            raise MCPError(
                INVALID_PARAMS, f"unknown resource {uri!r}; see resources/list and resources/templates/list"
            )
        try:
            store = project_store(match["id"], self.owner(ctx))
        except (ProjectNotFound, ProjectForbidden, PermissionError) as exc:
            raise MCPError(INVALID_PARAMS, str(exc)) from exc
        svc = ProjectService(store, DEFAULT_ENGINE, actor=self.actor(ctx))
        part = match["part"]
        payload: Any
        if part is None:
            payload = _info(store.row()).model_dump(mode="json")
        elif part == "flowsheet":
            payload = svc.flowsheet()
        elif part == "results":
            payload = svc.results()
        elif part == "trace":
            payload = svc.engine.trace_project(store.get())[1].model_dump(mode="json")
        else:
            payload = {"changes": [change_payload(c) for c in store.changes(limit=500)]}
        return json.dumps(payload, default=str)

    # -- the SDK server -------------------------------------------------------------------

    def server(self) -> Server[Any]:
        async def list_tools(
            ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
        ) -> types.ListToolsResult:
            return types.ListToolsResult(tools=self.tools())

        async def call_tool(
            ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
        ) -> types.CallToolResult:
            args = dict(params.arguments or {})
            return await anyio.to_thread.run_sync(self.call, ctx, params.name, args)

        async def list_resources(
            ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
        ) -> types.ListResourcesResult:
            return types.ListResourcesResult(resources=await anyio.to_thread.run_sync(self.resources, ctx))

        async def list_resource_templates(
            ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
        ) -> types.ListResourceTemplatesResult:
            return types.ListResourceTemplatesResult(resource_templates=self.templates())

        async def read_resource(
            ctx: ServerRequestContext[Any, Any], params: types.ReadResourceRequestParams
        ) -> types.ReadResourceResult:
            uri = str(params.uri)
            text = await anyio.to_thread.run_sync(self.read, ctx, uri)
            return types.ReadResourceResult(
                contents=[types.TextResourceContents(uri=uri, mime_type="application/json", text=text)]
            )

        return Server(
            SERVER_NAME,
            version="1.0.0",
            title="Stomato process simulator",
            instructions=INSTRUCTIONS,
            on_list_tools=list_tools,
            on_call_tool=call_tool,
            on_list_resources=list_resources,
            on_list_resource_templates=list_resource_templates,
            on_read_resource=read_resource,
        )


def build_server(*, owner: str | None = None, project_id: str | None = None) -> Server[Any]:
    """The configured SDK server (tests connect an MCP client to it in memory)."""
    return StomatoMCP(owner=owner, project_id=project_id).server()


ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]
]


def require_bearer(app: ASGIApp) -> ASGIApp:
    """ASGI wrapper: with ``STOMATO_API_TOKENS`` set, 401 any HTTP request
    without a known bearer token (tokens never logged or echoed)."""

    async def wrapped(scope: dict[str, Any], receive: Any, send: Any) -> None:
        state = auth.auth_state()
        if scope.get("type") == "http" and state.tokens is not None:
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            scheme, _, token = headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or token.strip() not in state.tokens:
                body = json.dumps(
                    {"error": {"code": "unauthorized", "message": "Bearer token required"}}
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await app(scope, receive, send)

    return wrapped


def http_app(*, host: str = "127.0.0.1", owner: str | None = None, project_id: str | None = None) -> ASGIApp:
    """The streamable-HTTP ASGI app (path ``/mcp``), bearer-checked."""
    server = build_server(owner=owner, project_id=project_id)
    app = server.streamable_http_app(host=host)
    return require_bearer(app)


def main(argv: list[str] | None = None) -> int:
    """``stomato-mcp`` console entry point."""
    parser = argparse.ArgumentParser(prog="stomato-mcp", description="Stomato MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    parser.add_argument("--project", default=None, help=f"Start on this project id (or ${PROJECT_ENV})")
    parser.add_argument(
        "--owner", default=None, help=f"Owner for stdio sessions (or ${OWNER_ENV}; default local)"
    )
    args = parser.parse_args(argv)
    init_db()
    if args.transport == "stdio":
        server = build_server(owner=args.owner, project_id=args.project)

        async def run_stdio() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        anyio.run(run_stdio)
        return 0
    import uvicorn

    uvicorn.run(
        http_app(host=args.host, owner=args.owner, project_id=args.project),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
    return 0


__all__ = ["INSTRUCTIONS", "SERVER_NAME", "StomatoMCP", "build_server", "http_app", "main", "require_bearer"]
