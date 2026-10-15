"""B-03 acceptance: GET /api/views/pfd.svg serves the S-22 renderer's SVG with
layout.pfd placement overrides — a placed unit renders at its stored position,
unplaced units auto-layout — and matches the CLI's out/pfd.svg byte-for-byte
for the sample slice."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from ngdesign import cli
from ngdesign.api.app import app
from ngdesign.render.pfd_svg import _unit_size
from ngdesign.render.symbols import _fmt

c = TestClient(app)

SVG_NS = "http://www.w3.org/2000/svg"


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _project() -> dict[str, Any]:
    r = c.get("/api/project")
    assert r.status_code == 200
    payload: dict[str, Any] = r.json()
    return payload


def _unit_tags(project: dict[str, Any]) -> list[str]:
    return [u["tag"] for u in project["flowsheet"]["units"]]


def _stream_ids(project: dict[str, Any]) -> list[str]:
    return [s["id"] for s in project["flowsheet"]["streams"]]


def _tagged_labels(svg: str) -> dict[str, tuple[str, str]]:
    """Map data-tag -> (x, y) of the self-labelled text inside its data-tag group
    (unit tag labels and stream-number ids)."""
    root = ET.fromstring(svg)
    labels: dict[str, tuple[str, str]] = {}
    for g in root.iter(f"{{{SVG_NS}}}g"):
        tag = g.get("data-tag")
        if tag is None:
            continue
        for text in g.iter(f"{{{SVG_NS}}}text"):
            if text.text == tag:
                labels[tag] = (text.get("x", ""), text.get("y", ""))
                break
    return labels


def test_pfd_view_matches_cli_out_pfd_svg(tmp_path: Path) -> None:
    """Parity anchor: API response == the CLI demo's out/pfd.svg for the slice."""
    _reset()
    assert cli.main(["slice", "--out", str(tmp_path)]) == 0
    cli_svg = (tmp_path / "pfd.svg").read_text()
    r = c.get("/api/views/pfd.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text == cli_svg


def test_every_unit_and_stream_group_carries_data_tag() -> None:
    _reset()
    root = ET.fromstring(c.get("/api/views/pfd.svg").text)
    tagged = {g.get("data-tag") for g in root.iter(f"{{{SVG_NS}}}g") if g.get("data-tag")}
    project = _project()
    assert tagged == set(_unit_tags(project)) | set(_stream_ids(project))


def test_placed_unit_renders_at_stored_position() -> None:
    _reset()
    project = _project()
    tag = sorted(_unit_tags(project))[0]
    kind = next(u["kind"] for u in project["flowsheet"]["units"] if u["tag"] == tag)

    before = _tagged_labels(c.get("/api/views/pfd.svg").text)
    assert c.put(f"/api/project/layout/pfd/{tag}", json={"x": 300.0, "y": 200.0}).status_code == 200
    after = _tagged_labels(c.get("/api/views/pfd.svg").text)

    # Placed tag: label sits at the stored centre (x = cx, y = cy - h/2 - 5).
    _, h = _unit_size(kind)
    assert after[tag] == ("300", _fmt(200.0 - h / 2 - 5.0))
    # Unplaced units keep their auto-layout positions (streams re-route, so
    # only unit tags are compared here).
    unit_tags = set(_unit_tags(project))
    others = unit_tags - {tag}
    assert all(after[t] == before[t] for t in others)
    # Sanity: the placement actually moved the tag.
    assert before[tag] != after[tag]


def test_stale_layout_tag_is_ignored() -> None:
    """A layout entry for a tag that is not in the flowsheet changes nothing."""
    _reset()
    base = c.get("/api/views/pfd.svg").text
    assert c.put("/api/project/layout/pfd/GONE", json={"x": 1.0, "y": 2.0}).status_code == 200
    assert c.get("/api/views/pfd.svg").text == base
