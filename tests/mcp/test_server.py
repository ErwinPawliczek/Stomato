"""stomato-mcp driven by the official MCP client (docs/agentic-layer.md section 6).

In memory (every tool surface and resource), over stdio (the console module as
a subprocess) and over streamable HTTP (uvicorn on a loopback port, bearer auth).
No network beyond loopback; no LLM.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import anyio
import httpx
import pytest
import uvicorn
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult, Implementation, TextResourceContents

from ngdesign.agent.tools import TOOLS
from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.mcp.server import build_server, http_app
from ngdesign.store import DbProjectStore, create_project

PLACE = {
    "kind": "cooler",
    "tag": "E-201",
    "params": None,
    "position": None,
    "grid": {"q": 3, "r": 0},
    "view": None,
}


def _run(fn: Callable[[], Awaitable[None]]) -> None:
    anyio.run(fn)


def _payload(result: CallToolResult) -> dict[str, Any]:
    text = result.content[0].text  # type: ignore[union-attr]
    data: dict[str, Any] = json.loads(text)
    return data


def _project(name: str = "mcp") -> str:
    row = create_project(name=name, owner="local", project=Project(name=name, flowsheet=slice_fs.build()))
    return row.id


def _client(target: Any) -> Client:
    return Client(target, client_info=Implementation(name="pytest", version="1"), cache=None)


def test_in_memory_tools_resources_and_history() -> None:
    pid = _project()

    async def main() -> None:
        async with _client(build_server()) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert {t.name for t in TOOLS} | {"list_projects", "create_project", "open_project"} == set(tools)
            place = tools["place_unit"]
            assert place.input_schema["properties"]["project_id"]["type"] == "string"
            assert "project_id" not in place.input_schema["required"]
            assert (
                tools["solve"].annotations is not None and tools["solve"].annotations.read_only_hint is True
            )

            listed = _payload(await client.call_tool("list_projects", {}))
            assert pid in {p["id"] for p in listed["projects"]}
            opened = _payload(await client.call_tool("open_project", {"project_id": pid}))
            assert opened["current"] == pid

            placed = await client.call_tool("place_unit", PLACE)
            assert not placed.is_error, placed
            body = _payload(placed)
            assert body["added"] == "E-201"
            assert body["change"]["actor"] == "mcp:pytest"
            assert "+ unit E-201 (cooler)" in body["change"]["lines"]
            assert placed.structured_content == body

            dup = await client.call_tool("place_unit", PLACE)
            assert dup.is_error and _payload(dup)["code"] == "duplicate_tag"

            value = _payload(await client.call_tool("read_results", {"address": "S-003.T", "unit": "degC"}))
            assert value["unit"] == "degC"
            explained = _payload(await client.call_tool("explain_value", {"address": "S-003.T"}))
            assert explained["steps"]

            undone = _payload(await client.call_tool("undo", {}))
            assert undone["undo"] == 1
            assert "E-201" not in {u.tag for u in DbProjectStore(pid).get().flowsheet.units}

            uris = {str(r.uri) for r in (await client.list_resources()).resources}
            assert {"stomato://projects", "stomato://catalogue/units", f"stomato://projects/{pid}"} <= uris
            templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
            assert "stomato://projects/{project_id}/trace" in templates

            for part, key in (("", "project"), ("/flowsheet", "units"), ("/results", "converged"),
                              ("/trace", "values"), ("/changes", "changes")):  # fmt: skip
                read = await client.read_resource(f"stomato://projects/{pid}{part}")
                contents = read.contents[0]
                assert isinstance(contents, TextResourceContents)
                assert key in json.loads(contents.text), part
            changes = json.loads(
                (await client.read_resource(f"stomato://projects/{pid}/changes")).contents[0].text  # type: ignore[union-attr]
            )["changes"]
            assert [c["kind"] for c in changes] == ["edit", "undo"]

    _run(main)


def test_in_memory_project_selection_and_errors() -> None:
    _project("a")
    other = _project("b")

    async def main() -> None:
        async with _client(build_server()) as client:
            created = _payload(
                await client.call_tool("create_project", {"name": "fresh", "template": "slice"})
            )
            assert created["current"] is True
            got = _payload(await client.call_tool("get_project", {}))
            assert got["name"] == "fresh"
            explicit = _payload(await client.call_tool("get_project", {"project_id": other}))
            assert explicit["name"] == "b"
            missing = await client.call_tool("get_project", {"project_id": "nope"})
            assert missing.is_error and "nope" in _payload(missing)["error"]
            unknown = await client.call_tool("no_such_tool", {})
            assert unknown.is_error
            with pytest.raises(Exception, match="unknown resource"):
                await client.read_resource("stomato://elsewhere")

    _run(main)


def test_default_project_is_the_owners_default() -> None:
    async def main() -> None:
        async with _client(build_server()) as client:
            got = _payload(await client.call_tool("get_project", {}))
            assert "V-101" in {u["tag"] for u in got["flowsheet"]["units"]}

    _run(main)


def test_stdio_subprocess_round_trip() -> None:
    pid = _project("stdio")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ngdesign.mcp", "--project", pid],
        env={**os.environ},
    )

    async def main() -> None:
        async with _client(params) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "place_unit" in names
            placed = await client.call_tool("place_unit", PLACE)
            assert not placed.is_error, placed

    _run(main)
    assert "E-201" in {u.tag for u in DbProjectStore(pid).get().flowsheet.units}
    assert DbProjectStore(pid).changes()[0].actor == "mcp:pytest"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def http_server() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(http_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=10)


def test_streamable_http_round_trip(http_server: str) -> None:
    pid = _project("http")

    async def main() -> None:
        async with _client(http_server) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "explain_value" in names
            placed = await client.call_tool("place_unit", {**PLACE, "project_id": pid})
            assert not placed.is_error, placed

    _run(main)
    assert "E-201" in {u.tag for u in DbProjectStore(pid).get().flowsheet.units}


def test_streamable_http_requires_bearer_when_tokens_set(
    http_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ngdesign.api import auth

    monkeypatch.setenv("STOMATO_API_TOKENS", "secret-token:alice")
    auth.reset_auth_cache()
    r = httpx.post(http_server, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert "secret-token" not in r.text
