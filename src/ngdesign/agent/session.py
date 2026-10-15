"""Scripted agent session (spec B-08): one engineering session driven over the HTTP API.

The recipe — create/reset, edit layout, solve, place every unit in all three
views, route, export every view, round-trip — is the L8 capstone: when it
passes end to end, the backend is drivable by any client (UI, agent, CI job)
and F-08 can wrap it. Steps are pure functions of a Transport (the only seam
through which the session touches the world) plus plain inputs, so the same
recipe drives ``fastapi.testclient.TestClient`` in the L8 gate test and the
stdlib urllib client in ``scripts/agent_session.py`` against a live server.

Determinism: no clock, no randomness, sorted iteration everywhere, no
timestamps in outputs — two consecutive runs are byte-identical.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol
from xml.etree import ElementTree as ET

SVG_MEDIA_TYPE = "image/svg+xml"

#: The views the session exports, in recipe order.
VIEWS: tuple[str, ...] = ("pfd", "pid", "plot")

#: The recipe: step names in the order the runner executes them.
RECIPE: tuple[str, ...] = ("create", "edit_layout", "solve", "place", "route", "export", "roundtrip")


@dataclass(frozen=True)
class HttpResult:
    """One HTTP response: status, content type, body."""

    status_code: int
    content_type: str
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


class Transport(Protocol):
    """The only seam through which the session touches the world."""

    def request(self, method: str, path: str, json_body: Any | None = None) -> HttpResult: ...


class StepError(RuntimeError):
    """Clean abort on the first failed call or assertion: names the step, status and detail."""

    def __init__(self, step: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"step {step!r}: {message}")
        self.step = step
        self.status_code = status_code


def polyline_length_mm(line: dict[str, Any]) -> float:
    """Routed length of one line: summed component centreline lengths (mm)."""
    total = 0.0
    for comp in line["components"]:
        start, end = comp["start"], comp["end"]
        total += math.dist((start["x"], start["y"], start["z"]), (end["x"], end["y"], end["z"]))
    return total


def data_tag_values(svg: str) -> set[str]:
    """Every data-tag attribute value in a rendered view (units, streams, line runs)."""
    root = ET.fromstring(svg)
    return {element.attrib["data-tag"] for element in root.iter() if "data-tag" in element.attrib}


def _require(step: str, condition: bool, message: str) -> None:
    if not condition:
        raise StepError(step, message)


def _clip(body: bytes, limit: int = 200) -> str:
    return body.decode("utf-8", errors="replace")[:limit]


def _detail(result: HttpResult) -> str:
    """FastAPI error bodies are ``{"detail": ...}``; fall back to the raw body."""
    try:
        payload = result.json()
    except ValueError:
        return _clip(result.body)
    if isinstance(payload, dict) and payload.get("detail") is not None:
        return _clip(str(payload["detail"]).encode("utf-8"))
    return _clip(result.body)


def _expect(step: str, result: HttpResult, *ok: int) -> None:
    """Abort unless the call answered with one of the accepted statuses."""
    if result.status_code not in ok:
        raise StepError(step, f"HTTP {result.status_code} — {_detail(result)}", result.status_code)


def step_create(transport: Transport) -> dict[str, Any]:
    """Create = reset to the seeded sample slice, then read it back."""
    step = "create"
    _expect(step, transport.request("POST", "/api/project/reset"), 200)
    result = transport.request("GET", "/api/project")
    _expect(step, result, 200)
    project: dict[str, Any] = result.json()
    tags = sorted(unit["tag"] for unit in project["flowsheet"]["units"])
    _require(step, "V-101" in tags, f"sample slice did not load: no V-101 in {tags}")
    _require(step, all(s["service"] for s in project["flowsheet"]["streams"]), "a stream has no service")
    return project


def step_edit_layout(transport: Transport, project: dict[str, Any]) -> dict[str, Any]:
    """Edit = reposition one unit's layout entry (create it if absent) and commit with PUT."""
    step = "edit_layout"
    tag = sorted(unit["tag"] for unit in project["flowsheet"]["units"])[0]
    current = project["layout"]["pfd"].get(tag, {"x": 0.0, "y": 0.0})
    moved = {"x": float(current["x"]) + 100.0, "y": float(current["y"]) + 50.0}
    project["layout"]["pfd"][tag] = moved
    result = transport.request("PUT", "/api/project", json_body=project)
    _expect(step, result, 200)
    edited: dict[str, Any] = result.json()
    _require(step, edited["layout"]["pfd"][tag] == moved, f"PUT response did not echo the {tag} placement")
    return edited


def step_solve(transport: Transport) -> dict[str, Any]:
    """Solve: converged, with a stream state for every flowsheet stream."""
    step = "solve"
    result = transport.request("POST", "/api/solve")
    _expect(step, result, 200)
    solved: dict[str, Any] = result.json()
    _require(step, solved["converged"] is True, "sample slice did not converge; nothing to draw")
    missing = {s["id"] for s in solved["flowsheet"]["streams"]} - set(solved["streams"])
    _require(step, not missing, f"no stream state for {sorted(missing)}")
    return solved


def step_place_all(transport: Transport, project: dict[str, Any]) -> dict[str, Any]:
    """Place every unit in all three views: pfd and pid (XY), plot (Vec3, mm)."""
    step = "place"
    tags = sorted(unit["tag"] for unit in project["flowsheet"]["units"])
    for i, tag in enumerate(tags):
        xy = {"x": float(120 * (i + 1)), "y": float(80 * (i + 1))}
        plot_mm = {"x": 6000.0 * (i + 1), "y": 6000.0, "z": 2000.0}
        for view, pos in (("pfd", xy), ("pid", xy)):
            result = transport.request("PUT", f"/api/project/layout/{view}/{tag}", json_body=pos)
            _expect(step, result, 200)
            _require(step, result.json()[view][tag] == pos, f"layout.{view}[{tag}] did not record {pos}")
        result = transport.request("PUT", f"/api/project/layout/plot/{tag}", json_body=plot_mm)
        _expect(step, result, 200)
        _require(step, result.json()["plot"][tag] == plot_mm, f"layout.plot[{tag}] did not record {plot_mm}")
        project["layout"]["pfd"][tag] = xy
        project["layout"]["pid"][tag] = xy
        project["layout"]["plot"][tag] = plot_mm
    return project


def step_route(transport: Transport) -> dict[str, Any]:
    """Route: every P&ID line gets a routed polyline with positive length."""
    step = "route"
    result = transport.request("POST", "/api/route")
    _expect(step, result, 200)
    net: dict[str, Any] = result.json()
    _require(step, bool(net["lines"]), "routing produced no lines")
    for line in net["lines"]:
        _require(
            step,
            polyline_length_mm(line) > 0.0,
            f"line {line['line_number']!r} has no routed geometry with positive length",
        )
    return net


def step_export(transport: Transport, project: dict[str, Any]) -> dict[str, bytes]:
    """Export every view; each drawing must show the placed units."""
    step = "export"
    tags = sorted(unit["tag"] for unit in project["flowsheet"]["units"])
    svgs: dict[str, bytes] = {}
    for view in VIEWS:
        result = transport.request("GET", f"/api/views/{view}.svg")
        _expect(step, result, 200)
        _require(step, result.content_type.startswith(SVG_MEDIA_TYPE), f"{view}.svg: not image/svg+xml")
        svg = result.body.decode("utf-8")
        _require(step, "<svg" in svg, f"{view}.svg has no <svg> root element")
        shown = data_tag_values(svg)
        missing = [tag for tag in tags if tag not in shown]
        _require(step, not missing, f"{view}.svg does not show placed units {missing}")
        svgs[f"{view}.svg"] = result.body
    return svgs


def step_roundtrip(transport: Transport, expected_layout: dict[str, Any]) -> dict[str, Any]:
    """Reload the project: the placements survived (edit, save, reload)."""
    step = "roundtrip"
    result = transport.request("GET", "/api/project")
    _expect(step, result, 200)
    project: dict[str, Any] = result.json()
    _require(step, project["layout"] == expected_layout, "reloaded project lost the placements")
    return project


@dataclass(frozen=True)
class SessionReport:
    """Everything one session run produced, in recipe order."""

    steps: tuple[str, ...]
    project: dict[str, Any]  # final project, reloaded from the server after the round-trip
    routed: dict[str, Any]  # POST /api/route: the routed network JSON
    svgs: dict[str, bytes]  # view file name -> rendered SVG bytes


def run_session(transport: Transport) -> SessionReport:
    """The full recipe; the first failed call or assertion aborts with a StepError."""
    project = step_create(transport)
    project = step_edit_layout(transport, project)
    step_solve(transport)
    project = step_place_all(transport, project)
    routed = step_route(transport)
    svgs = step_export(transport, project)
    project = step_roundtrip(transport, project["layout"])
    return SessionReport(steps=RECIPE, project=project, routed=routed, svgs=svgs)


def determinism_problems(first: SessionReport, second: SessionReport) -> list[str]:
    """Byte-level checks between two consecutive runs: the SVGs and the route result."""
    problems = [
        f"{name} changed between runs" for name in sorted(first.svgs) if first.svgs[name] != second.svgs[name]
    ]
    if json.dumps(first.routed, sort_keys=True) != json.dumps(second.routed, sort_keys=True):
        problems.append("route result changed between runs")
    return problems
