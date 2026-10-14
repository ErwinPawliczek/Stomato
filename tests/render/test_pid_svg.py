"""Tests for the S-18 P&ID SVG renderer."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from ngdesign.contracts import (
    PID,
    InlineItem,
    InlineKind,
    Instrument,
    Valve,
    ValveType,
)
from ngdesign.flowsheets.samples import sample_pid
from ngdesign.registry import available, create
from ngdesign.render.pid_svg import render_pid_svg

SVG_NS = "http://www.w3.org/2000/svg"


def _rules_applied(pid: PID) -> PID:
    """Apply every registered pid_rule in registry order (no-op until S-23.. land)."""
    for name in available("pid_rule"):
        pid = create("pid_rule", name).apply(pid)
    return pid


def _text_contents(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return [el.text for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "text" and el.text]


def _bbox_rects(svg: str) -> list[tuple[float, float, float, float, str]]:
    root = ET.fromstring(svg)
    rects = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "rect" and el.get("class") == "equipment-bbox":
            rects.append(
                (
                    float(el.get("x", "0")),
                    float(el.get("y", "0")),
                    float(el.get("width", "0")),
                    float(el.get("height", "0")),
                    el.get("data-tag", ""),
                )
            )
    return rects


def test_registered_as_diagram_pid() -> None:
    assert "pid" in available("diagram")
    renderer = create("diagram", "pid")
    assert callable(renderer.render)


def test_render_sample_pid_wellformed_svg() -> None:
    svg = render_pid_svg(sample_pid())
    root = ET.fromstring(svg)  # raises if not well-formed XML
    assert root.tag == f"{{{SVG_NS}}}svg"


def test_render_after_rules_wellformed_svg() -> None:
    pid = _rules_applied(sample_pid())
    svg = render_pid_svg(pid)
    root = ET.fromstring(svg)
    assert root.tag == f"{{{SVG_NS}}}svg"


def test_every_tag_appears_as_text() -> None:
    pid = sample_pid()
    texts = set(_text_contents(render_pid_svg(pid)))
    for eq in pid.equipment:
        assert eq.tag in texts, f"equipment tag {eq.tag} missing"
    for line in pid.lines:
        assert line.number in texts, f"line number {line.number} missing"


def test_valve_and_instrument_tags_appear_as_text() -> None:
    pid = sample_pid()
    # Enrich the bare sample with a valve, an inline item and two instruments.
    pid.lines[0].items = [
        InlineItem(kind=InlineKind.VALVE, ref="XV-1001"),
        InlineItem(kind=InlineKind.DRAIN),
    ]
    pid.valves = [Valve(tag="XV-1001", type=ValveType.ESD, nps_in=8, flange_class=300)]
    pid.instruments = [
        Instrument(tag="PT-1001", function="PT", loop=1001, connected_to="V-101"),
        Instrument(tag="PDIT-1002", function="PDIT", loop=1002, connected_to='8"-PG-1001-B1'),
    ]
    texts = set(_text_contents(render_pid_svg(pid)))
    assert "XV-1001" in texts
    for inst in pid.instruments:
        assert inst.tag in texts, f"instrument tag {inst.tag} missing"


def test_no_two_equipment_bboxes_overlap() -> None:
    rects = _bbox_rects(render_pid_svg(sample_pid()))
    assert len(rects) == len(sample_pid().equipment)
    for i, (x1, y1, w1, h1, tag1) in enumerate(rects):
        for x2, y2, w2, h2, tag2 in rects[i + 1 :]:
            overlap_x = min(x1 + w1, x2 + w2) - max(x1, x2)
            overlap_y = min(y1 + h1, y2 + h2) - max(y1, y2)
            assert overlap_x <= 0 or overlap_y <= 0, f"bounding boxes of {tag1} and {tag2} overlap"


def test_equipment_left_to_right_in_line_topology() -> None:
    # V-101 -> K-101 through 8"-PG-1002-B1, so V-101 must sit left of K-101.
    rects = {r[4]: r for r in _bbox_rects(render_pid_svg(sample_pid()))}
    assert rects["V-101"][0] < rects["K-101"][0]
    assert rects["V-101"][0] < rects["P-101"][0]


def test_render_is_deterministic() -> None:
    pid = _rules_applied(sample_pid())
    assert render_pid_svg(pid) == render_pid_svg(pid)


def test_loose_valve_still_labelled() -> None:
    pid = sample_pid()
    pid.valves = [
        Valve(tag="PSV-1003", type=ValveType.PSV, nps_in=3, flange_class=300, set_pressure_Pa=4.4e6)
    ]
    texts = set(_text_contents(render_pid_svg(pid)))
    assert "PSV-1003" in texts
