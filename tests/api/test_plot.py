"""B-05 acceptance: POST /api/route and GET /api/views/plot.svg serve the S-21
orthogonal router's output for the current project through the layout.plot
placements. With an empty layout.plot the routed network is exactly the S-35
CLI demo's route(pid, layout={}) — 13 lines, identical geometry — and moving
equipment via PUT /api/project/layout/plot/{tag} re-routes the lines that
touch it (routed lengths follow the equipment).
"""

from __future__ import annotations

import math
from typing import Any
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api.app import app
from ngdesign.api.routes_plot import MARGIN_MM, _extent, render_plot_svg
from ngdesign.cli import _apply_rules, _rule_set, _run_sizers, _solve_slice, _violations
from ngdesign.contracts import PID, PipingNetwork

c = TestClient(app)

SVG_NS = "http://www.w3.org/2000/svg"


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _slice_pid() -> PID:
    """The exact chain the plot routes: solve -> sizers -> builder -> rules."""
    solved = _run_sizers(_solve_slice())
    pid = registry.create("pid_builder", "default").build(solved)
    rules = _rule_set(solved)
    pid = _apply_rules(pid, rules)
    assert _violations(pid, rules) == []  # the slice is violation-free
    return pid


def _route_json() -> dict[str, Any]:
    r = c.post("/api/route")
    assert r.status_code == 200
    return r.json()


def _plot_svg() -> str:
    r = c.get("/api/views/plot.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    return r.text


def _lengths(net_json: dict[str, Any]) -> dict[str, float]:
    """Routed length per line number: summed component centreline lengths (mm)."""
    out: dict[str, float] = {}
    for line in net_json["lines"]:
        total = 0.0
        for comp in line["components"]:
            s, e = comp["start"], comp["end"]
            total += math.dist((s["x"], s["y"], s["z"]), (e["x"], e["y"], e["z"]))
        out[line["line_number"]] = total
    return out


def _tagged_groups(svg: str) -> set[str]:
    root = ET.fromstring(svg)
    return {g.get("data-tag") for g in root.iter(f"{{{SVG_NS}}}g") if g.get("data-tag")}


def _group_polylines(svg: str, tag: str) -> list[str]:
    """points= attributes of the polylines inside a data-tag group."""
    root = ET.fromstring(svg)
    return [
        p.get("points", "")
        for g in root.iter(f"{{{SVG_NS}}}g")
        if g.get("data-tag") == tag
        for p in g.iter(f"{{{SVG_NS}}}polyline")
    ]


def test_route_matches_cli_routing() -> None:
    """Parity anchor: an empty layout.plot routes exactly like the CLI demo."""
    _reset()
    pid = _slice_pid()
    net = registry.create("router", "orthogonal").route(pid, {})
    assert len(net.lines) == 13

    api_lengths = _lengths(_route_json())
    assert set(api_lengths) == {line.line_number for line in net.lines}
    for line in net.lines:
        expected = sum(
            math.dist((comp.start.x, comp.start.y, comp.start.z), (comp.end.x, comp.end.y, comp.end.z))
            for comp in line.components
        )
        assert api_lengths[line.line_number] == pytest.approx(expected, rel=1e-12)


def test_plot_svg_is_the_routed_network_drawn() -> None:
    """GET /api/views/plot.svg draws exactly the network POST /api/route returns."""
    _reset()
    net = PipingNetwork.model_validate(_route_json())
    assert _plot_svg() == render_plot_svg(net)


def test_plot_svg_renders_equipment_and_lines() -> None:
    """Every equipment tag and line number is a data-tag group; 13 line runs."""
    _reset()
    pid = _slice_pid()
    svg = _plot_svg()
    expected = {e.tag for e in pid.equipment} | {ln.number for ln in pid.lines}
    assert _tagged_groups(svg) == expected
    assert len(expected) == 19  # 6 equipment + 13 routed lines
    root = ET.fromstring(svg)
    polylines = list(root.iter(f"{{{SVG_NS}}}polyline"))
    assert len(polylines) == 13
    assert all(len(p.get("points", "").split()) >= 2 for p in polylines)


def test_moving_equipment_reroutes_affected_lines() -> None:
    """L5: moving a unit in layout.plot re-routes the lines that touch it.

    The last equipment is moved deliberately: the S-21 router packs unplaced
    tags into the leading 12 000 mm slots, so placing an earlier unit would
    renumber every later unit's auto position. Placing the last unit leaves
    all other auto positions untouched, isolating the re-routing effect.
    """
    _reset()
    pid = _slice_pid()
    tag = pid.equipment[-1].tag  # default router placement puts it at x = 72 000
    touching = {ln.number for ln in pid.lines if tag in (ln.start.equipment, ln.end.equipment)}
    assert touching

    before_lengths = _lengths(_route_json())
    before_svg = _plot_svg()

    r = c.put(f"/api/project/layout/plot/{tag}", json={"x": 72000.0, "y": 20000.0, "z": 0.0})
    assert r.status_code == 200

    after_lengths = _lengths(_route_json())
    after_svg = _plot_svg()

    assert set(after_lengths) == set(before_lengths)  # same 13 lines, re-routed
    for number, length in before_lengths.items():
        if number in touching:
            assert after_lengths[number] > length  # pulled 20 m north: longer run
        else:
            assert after_lengths[number] == pytest.approx(length, rel=1e-12)
    assert after_svg != before_svg
    for number in touching:
        assert _group_polylines(after_svg, number) != _group_polylines(before_svg, number)


def test_plot_placement_follows_layout_plot() -> None:
    """A placed tag sits at the stored plot position, drawn plan north up."""
    _reset()
    tag = _slice_pid().equipment[0].tag
    base_svg = _plot_svg()

    r = c.put(f"/api/project/layout/plot/{tag}", json={"x": 12000.0, "y": 20000.0, "z": 0.0})
    assert r.status_code == 200

    net_json = _route_json()
    env = next(e for e in net_json["equipment"] if e["tag"] == tag)
    assert env["min"] == {"x": 11000.0, "y": 19000.0, "z": -1000.0}
    assert env["max"] == {"x": 13000.0, "y": 21000.0, "z": 1000.0}

    # The SVG label sits at the envelope centre in the plan projection.
    svg = _plot_svg()
    assert svg != base_svg
    min_x, _min_y, _max_x, max_y = _extent(PipingNetwork.model_validate(net_json))
    g = next(g for g in ET.fromstring(svg).iter(f"{{{SVG_NS}}}g") if g.get("data-tag") == tag)
    text = next(t for t in g.iter(f"{{{SVG_NS}}}text"))
    assert float(text.get("x", "")) == 12000.0 - min_x + MARGIN_MM
    assert float(text.get("y", "")) == max_y + MARGIN_MM - 20000.0


def test_plot_ignores_stale_placement_tag() -> None:
    """A layout.plot entry for a tag that is not in the P&ID changes nothing."""
    _reset()
    base_svg = _plot_svg()
    base_route = _route_json()
    assert c.put("/api/project/layout/plot/GONE", json={"x": 1.0, "y": 2.0, "z": 3.0}).status_code == 200
    assert _plot_svg() == base_svg
    assert _route_json() == base_route


def test_unknown_unit_kind_answers_501() -> None:
    """A project with no plugin for a unit kind cannot be routed: 501, like solve."""
    _reset()
    project = c.get("/api/project").json()
    project["flowsheet"]["units"][0]["kind"] = "missing_kind"
    assert c.put("/api/project", json=project).status_code == 200
    assert c.post("/api/route").status_code == 501
    assert c.get("/api/views/plot.svg").status_code == 501
