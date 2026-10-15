"""B-08 acceptance: the L8 gate — one deterministic scripted session drives the
whole product headless over the HTTP surface (TestClient), asserting at every
step; the CLI maps aborts to non-zero exits and writes every artifact.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from ngdesign.agent.session import (
    HttpResult,
    StepError,
    Transport,
    polyline_length_mm,
    run_session,
)
from ngdesign.api.app import app

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # the CLI script lives outside the installed package
    sys.path.insert(0, str(ROOT))

from scripts.agent_session import main  # noqa: E402


class ApiTransport:
    """Adapt fastapi.testclient.TestClient to the session Transport protocol."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def request(self, method: str, path: str, json_body: Any | None = None) -> HttpResult:
        response = self._client.request(method, path, json=json_body)
        return HttpResult(response.status_code, response.headers.get("content-type", ""), response.content)


def transport() -> ApiTransport:
    return ApiTransport(TestClient(app))


def _lengths(routed: dict[str, Any]) -> dict[str, float]:
    """Routed length per line number (mm): the shared polyline length over components."""
    return {line["line_number"]: polyline_length_mm(line) for line in routed["lines"]}


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


class _SabotageTransport:
    """Transport double: one method+path answers with a canned error; the rest pass through."""

    def __init__(self, inner: Transport, method: str, path: str, status_code: int, detail: str) -> None:
        self._inner = inner
        self._method = method
        self._path = path
        self._status_code = status_code
        self._detail = detail

    def request(self, method: str, path: str, json_body: Any | None = None) -> HttpResult:
        if (method, path) == (self._method, self._path):
            body = json.dumps({"detail": self._detail}).encode("utf-8")
            return HttpResult(self._status_code, "application/json", body)
        return self._inner.request(method, path, json_body)


class _CorruptProjectPut:
    """Real failure path: sabotage the edit step's PUT body so the server 422s."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner

    def request(self, method: str, path: str, json_body: Any | None = None) -> HttpResult:
        if method == "PUT" and path == "/api/project" and json_body is not None:
            bad = copy.deepcopy(json_body)
            bad["flowsheet"]["units"][1]["tag"] = bad["flowsheet"]["units"][0]["tag"]  # duplicate unit tags
            return self._inner.request(method, path, bad)
        return self._inner.request(method, path, json_body)


def test_session_runs_end_to_end(tmp_path: Path) -> None:
    """The full scripted session over HTTP with no UI; the CLI exits 0 and writes every artifact."""
    report = run_session(transport())
    assert report.steps == ("create", "edit_layout", "solve", "place", "route", "export", "roundtrip")
    assert report.project["name"] == "slice"

    out = tmp_path / "session"
    assert main(["--out", str(out)], transport=transport()) == 0
    assert {p.name for p in out.iterdir()} == {
        "project.json",
        "route.json",
        "session.json",
        "pfd.svg",
        "pid.svg",
        "plot.svg",
    }


def test_session_is_deterministic(tmp_path: Path) -> None:
    """Two consecutive runs: byte-identical SVGs and route results."""
    client = transport()
    first = run_session(client)
    second = run_session(client)
    assert first.svgs == second.svgs
    assert _canonical(first.routed) == _canonical(second.routed)

    # the CLI's --check-determinism drives the same pair of runs and exits 0
    assert main(["--check-determinism", "--out", str(tmp_path / "det")], transport=transport()) == 0


def test_session_exports_all_views() -> None:
    """All three views export as SVG with the placements reflected in the drawings."""
    report = run_session(transport())
    placed = report.project["layout"]["plot"]
    assert set(report.svgs) == {"pfd.svg", "pid.svg", "plot.svg"}
    for name, svg in sorted(report.svgs.items()):
        root = ET.fromstring(svg.decode("utf-8"))
        assert root.tag.endswith("svg")
        shown = {element.attrib["data-tag"] for element in root.iter() if "data-tag" in element.attrib}
        missing = sorted(set(placed) - shown)
        assert not missing, f"{name} does not show placed units {missing}"
    # the routed envelopes sit exactly where the session placed each unit
    for env in report.routed["equipment"]:
        if env["tag"] not in placed:  # the P&ID can carry equipment the flowsheet did not place
            continue
        centre = {
            "x": (env["min"]["x"] + env["max"]["x"]) / 2,
            "y": (env["min"]["y"] + env["max"]["y"]) / 2,
            "z": (env["min"]["z"] + env["max"]["z"]) / 2,
        }
        assert centre == placed[env["tag"]], env["tag"]


def test_session_moving_equipment_changes_routed_lengths() -> None:
    """Re-asserts the B-05 invariant across the whole session: routed lengths follow the equipment."""
    client = transport()
    report = run_session(client)
    before = _lengths(report.routed)
    before_svg = report.svgs["plot.svg"]

    tag = "V-101"  # all units are explicitly placed, so moving one only moves its own runs
    moved = dict(report.project["layout"]["plot"][tag])
    moved["y"] += 20000.0  # pulled 20 m north
    response = client.request("PUT", f"/api/project/layout/plot/{tag}", json_body=moved)
    assert response.status_code == 200

    after = _lengths(client.request("POST", "/api/route").json())
    assert set(after) == set(before)  # same lines, re-routed
    changed = sorted(number for number in before if after[number] != pytest.approx(before[number], rel=1e-12))
    assert changed, "no routed length followed the moved equipment"
    for number in changed:
        assert after[number] > before[number]  # 20 m further north: every touched run got longer
    for number in sorted(set(before) - set(changed)):
        assert after[number] == pytest.approx(before[number], rel=1e-12)
    assert client.request("GET", "/api/views/plot.svg").body != before_svg  # the plan view moved too


def test_session_fails_loudly_on_error(tmp_path: Path) -> None:
    """4xx/5xx from any seam: StepError names step, status and detail; the CLI exits non-zero."""
    inner = transport()

    # Real 422 through the edit seam: duplicate unit tags fail the PUT-time contracts.
    with pytest.raises(StepError) as excinfo:
        run_session(_CorruptProjectPut(inner))
    assert excinfo.value.step == "edit_layout"
    assert excinfo.value.status_code == 422

    # 501 through the solve seam (unregistered unit kind), then the CLI's non-zero exit.
    failing = _SabotageTransport(
        inner, "POST", "/api/solve", 501, "unit kind 'missing_kind' has no registered plugin"
    )
    with pytest.raises(StepError) as excinfo:
        run_session(failing)
    assert excinfo.value.step == "solve"
    assert excinfo.value.status_code == 501
    assert "missing_kind" in str(excinfo.value)
    assert main(["--out", str(tmp_path / "abort")], transport=failing) == 1
