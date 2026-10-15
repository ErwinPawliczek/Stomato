"""B-06 acceptance: GET /api/views/iso, GET /api/views/iso/{line}.svg and
...{line}.json serve the S-19 fabrication isometric per routed line, honour
layout.iso placement overrides, and are byte-identical to the S-35 CLI demo's
out/iso_NN_<line>.svg for the sample slice (empty layout.iso).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from ngdesign import cli, registry
from ngdesign.api.app import app
from ngdesign.api.routes_iso import _iso_placements
from ngdesign.cli import _apply_rules, _iso_stem, _rule_set, _run_sizers, _solve_slice
from ngdesign.contracts import PID, PipingNetwork, RoutedLine
from ngdesign.flowsheets.samples import sample_pid, sample_routed_line

c = TestClient(app)

SVG_NS = "http://www.w3.org/2000/svg"


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200
    _iso_placements.clear()


def _u(part: str) -> str:
    """Percent-encode a path segment (line numbers carry inch marks)."""
    return quote(part, safe="")


def _routed_locally() -> tuple[PID, PipingNetwork]:
    """The exact chain the endpoints serve, computed locally as the oracle."""
    solved = _run_sizers(_solve_slice())
    pid = registry.create("pid_builder", "default").build(solved)
    pid = _apply_rules(pid, _rule_set(solved))
    return pid, registry.create("router", "orthogonal").route(pid, {})


def _local(tag: str) -> str:
    """Local name of a (possibly namespace-expanded) XML tag."""
    return tag.rsplit("}", 1)[-1]


def _tagged(root: ET.Element) -> set[str]:
    return {tag for g in root.iter(f"{{{SVG_NS}}}g") if (tag := g.get("data-tag"))}


def _get_svg(line_number: str) -> str:
    r = c.get(f"/api/views/iso/{_u(line_number)}.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    svg: str = r.text
    return svg


def _sheet_and_routed(line_number: str) -> tuple[dict[str, Any], RoutedLine]:
    """The IsoSheet JSON and the matching locally-routed line (the oracle)."""
    r = c.get(f"/api/views/iso/{_u(line_number)}.json")
    assert r.status_code == 200
    _, net = _routed_locally()
    routed = next(ln for ln in net.lines if ln.line_number == line_number)
    return r.json(), routed


def test_iso_listandservable() -> None:
    """Every routed line is listed and servable as valid SVG."""
    _reset()
    _, net = _routed_locally()
    expected = [ln.line_number for ln in net.lines]
    r = c.get("/api/views/iso")
    assert r.status_code == 200
    assert r.json() == expected
    assert expected != []  # the sample slice routes
    for line_number in expected:
        root = ET.fromstring(_get_svg(line_number))
        assert _local(root.tag) == "svg"


def test_iso_svg_unknown_line_404() -> None:
    """An unrouted stream number is a 404 on both the .svg and the .json."""
    _reset()
    streams = [s["id"] for s in c.get("/api/project").json()["flowsheet"]["streams"]]
    routed = set(c.get("/api/views/iso").json())
    unrouted = next(s for s in streams if s not in routed)
    assert c.get(f"/api/views/iso/{_u(unrouted)}.svg").status_code == 404
    assert c.get(f"/api/views/iso/{_u(unrouted)}.json").status_code == 404


def test_iso_svg_matches_cli_slice(tmp_path: Path) -> None:
    """Parity anchor: an empty layout.iso is byte-identical to out/iso_NN_<line>.svg."""
    _reset()
    assert cli.main(["slice", "--out", str(tmp_path)]) == 0
    lines = c.get("/api/views/iso").json()
    for i, line_number in enumerate(lines, start=1):
        assert _get_svg(line_number) == (tmp_path / f"{_iso_stem(i, line_number)}.svg").read_text()


def test_renderer_default_bytes_unchanged() -> None:
    """With no placements argument (or an empty dict) the renderer's output is
    byte-identical and carries no placement transforms — the placements
    parameter changes nothing by default."""
    renderer = registry.create("iso_renderer", "svg")
    default = renderer.render(sample_routed_line(), sample_pid())
    assert default.svg == renderer.render(sample_routed_line(), sample_pid(), placements={}).svg
    assert default.svg == renderer.render(sample_routed_line(), sample_pid(), placements=None).svg
    assert 'transform="translate' not in default.svg


def test_iso_json_bom_and_length_invariants() -> None:
    """The L6 invariants per line: BOM pipe metres sum to the routed pipe
    length, every drawn run dimension equals the stored run length, and the
    BOM grouping (identical descriptions merged, fittings in ea, pipe in m)
    is internally consistent."""
    _reset()
    for line_number in c.get("/api/views/iso").json():
        sheet, routed = _sheet_and_routed(line_number)
        components = routed.components
        pipes = [comp for comp in components if comp.kind.value == "pipe"]
        pipe_mm = sum(comp.length_mm for comp in pipes)
        assert sheet["total_pipe_length_mm"] == pytest.approx(pipe_mm, rel=1e-9)

        assert len({b["description"] for b in sheet["bom"]}) == len(sheet["bom"])
        m_rows = [b for b in sheet["bom"] if b["unit"] == "m"]
        assert sum(b["qty"] for b in m_rows) == pytest.approx(pipe_mm / 1000.0, rel=1e-9)
        for b in sheet["bom"]:
            if b["unit"] == "m":
                desc_mm = sum(comp.length_mm for comp in pipes if comp.description == b["description"])
                assert b["qty"] == pytest.approx(desc_mm / 1000.0, rel=1e-9)
            else:
                assert b["unit"] == "ea"
                assert b["qty"] == sum(1 for comp in components if comp.description == b["description"])

        # Per-run dimensions drawn in the SVG match the stored run lengths.
        root = ET.fromstring(sheet["svg"])
        dims = {
            g.get("data-tag"): cast("ET.Element[str]", g.find(f"{{{SVG_NS}}}text")).text
            for g in root.iter(f"{{{SVG_NS}}}g")
            if g.get("data-tag", "").startswith("dim-")
        }
        for comp in pipes:
            assert float(cast(str, dims[f"dim-{comp.id}"])) == pytest.approx(comp.length_mm, abs=0.05)


def test_iso_cut_list_matches_components() -> None:
    """Every cut piece equals its matching PIPE component's length."""
    _reset()
    for line_number in c.get("/api/views/iso").json():
        sheet, routed = _sheet_and_routed(line_number)
        pipes = [comp for comp in routed.components if comp.kind.value == "pipe"]
        assert [piece["piece"] for piece in sheet["cut_list"]] == list(range(1, len(pipes) + 1))
        assert [piece["length_mm"] for piece in sheet["cut_list"]] == pytest.approx(
            [comp.length_mm for comp in pipes]
        )
        assert all(
            piece["nps_in"] == comp.nps_in for piece, comp in zip(sheet["cut_list"], pipes, strict=True)
        )


def test_iso_svg_has_tagged_groups() -> None:
    """BOM descriptions, per-run dimensions, title block and BOM table all
    carry data-tag, and the tag set is stable across re-solves."""
    _reset()
    for line_number in c.get("/api/views/iso").json():
        sheet, routed = _sheet_and_routed(line_number)
        root = ET.fromstring(sheet["svg"])
        tagged = _tagged(root)
        assert {b["description"] for b in sheet["bom"]} <= tagged
        assert {"title-block", "bom"} <= tagged
        assert {f"dim-{comp.id}" for comp in routed.components if comp.kind.value == "pipe"} <= tagged
        # Tags stable across solves of the same project.
        again = ET.fromstring(_get_svg(line_number))
        assert _tagged(again) == tagged


def test_iso_svg_placement_override() -> None:
    """A layout.iso entry moves the tagged group to the stored position; a
    dimension group moves too."""
    _reset()
    line_number = c.get("/api/views/iso").json()[0]
    sheet, _ = _sheet_and_routed(line_number)
    base = _get_svg(line_number)

    description = sheet["bom"][0]["description"]
    put = c.put(f"/api/project/layout/iso/{_u(description)}", json={"x": 500.0, "y": 60.0})
    assert put.status_code == 200
    moved = _get_svg(line_number)
    assert moved != base
    root = ET.fromstring(moved)
    group = next(g for g in root.iter(f"{{{SVG_NS}}}g") if g.get("data-tag") == description)
    assert group.get("transform") == "translate(500.00 60.00)"

    _, routed = _sheet_and_routed(line_number)
    dim_tag = next(f"dim-{comp.id}" for comp in routed.components if comp.kind.value == "pipe")
    assert c.put(f"/api/project/layout/iso/{dim_tag}", json={"x": 10.0, "y": 20.0}).status_code == 200
    root2 = ET.fromstring(_get_svg(line_number))
    dim_group = next(g for g in root2.iter(f"{{{SVG_NS}}}g") if g.get("data-tag") == dim_tag)
    assert dim_group.get("transform") == "translate(10.00 20.00)"


def test_iso_svg_ignores_unknown_key() -> None:
    """Overrides for keys that match no data-tag group (unknown tags and line
    numbers, which are no tag namespace) are a byte-identical no-op."""
    _reset()
    line_number = c.get("/api/views/iso").json()[0]
    base = _get_svg(line_number)

    assert c.put("/api/project/layout/iso/XX-9999", json={"x": 1.0, "y": 2.0}).status_code == 200
    assert _get_svg(line_number) == base

    # A line number is not a BOM/dimension tag: overriding it is a no-op too.
    assert line_number not in _tagged(ET.fromstring(base))
    assert c.put(f"/api/project/layout/iso/{_u(line_number)}", json={"x": 3.0, "y": 4.0}).status_code == 200
    assert _get_svg(line_number) == base


def test_iso_routes_registered() -> None:
    """The three iso routes plus the placement PUT are registered on the app
    (one include_router line)."""
    paths = set(app.openapi()["paths"])
    assert "/api/views/iso" in paths
    assert "/api/views/iso/{line_number}.svg" in paths
    assert "/api/views/iso/{line_number}.json" in paths
    assert "/api/project/layout/iso/{key}" in paths


def test_solve_cache_untouched() -> None:
    """An iso view request leaves the cached solve result byte-identical (B-02):
    the sizers run on a deep copy inside the view chain."""
    _reset()
    before = c.post("/api/solve").json()
    line_number = c.get("/api/views/iso").json()[0]
    assert c.get(f"/api/views/iso/{_u(line_number)}.svg").status_code == 200
    assert c.get(f"/api/views/iso/{_u(line_number)}.json").status_code == 200
    assert c.post("/api/solve").json() == before
