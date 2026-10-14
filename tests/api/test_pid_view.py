"""B-04 acceptance: GET /api/views/pid.svg serves the S-33 builder + every
registered pid_rule rendered by S-18, honors layout.pid placement overrides,
and is byte-identical to the S-35 CLI demo's out/pid.svg for the sample slice
(13 lines over 6 equipment, 0 violations).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi.testclient import TestClient

from ngdesign import registry
from ngdesign.api.app import app
from ngdesign.cli import _apply_rules, _rule_set, _run_sizers, _solve_slice, _violations
from ngdesign.contracts import PID

c = TestClient(app)


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _slice_pid() -> PID:
    """The exact chain the endpoint serves, for tag-set expectations."""
    solved = _run_sizers(_solve_slice())
    pid = registry.create("pid_builder", "default").build(solved)
    rules = _rule_set(solved)
    pid = _apply_rules(pid, rules)
    assert _violations(pid, rules) == []  # parity anchor: the slice is violation-free
    return pid


def _local(tag: str) -> str:
    """Local name of a (possibly namespace-expanded) XML tag."""
    return tag.rsplit("}", 1)[-1]


def _get_svg() -> str:
    r = c.get("/api/views/pid.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    return r.text


def test_pid_svg_matches_cli_slice(tmp_path: Path) -> None:
    """Parity anchor: an empty layout.pid is byte-identical to out/pid.svg."""
    _reset()
    from ngdesign import cli

    assert cli.main(["slice", "--out", str(tmp_path)]) == 0
    assert _get_svg() == (tmp_path / "pid.svg").read_text()


def test_pid_svg_has_every_tag_and_data_tag() -> None:
    """Every equipment tag, line number, valve tag and instrument tag appears
    as text, and data-tag attributes mark equipment, lines, valves, instruments."""
    _reset()
    pid = _slice_pid()
    root = ET.fromstring(_get_svg())
    texts = {el.text for el in root.iter() if _local(el.tag) == "text" and el.text}
    tagged = {el.get("data-tag") for el in root.iter() if el.get("data-tag")}

    eq_tags = {e.tag for e in pid.equipment}
    assert len(eq_tags) == 6
    assert len(pid.lines) == 13
    for tags in (
        eq_tags,
        {ln.number for ln in pid.lines},
        {v.tag for v in pid.valves},
        {i.tag for i in pid.instruments},
    ):
        assert tags <= texts
        assert tags <= tagged


def test_pid_svg_placement_override() -> None:
    """A placed tag renders at the stored layout.pid position; others auto-layout."""
    _reset()
    first_eq = sorted(e.tag for e in _slice_pid().equipment)[0]
    base = _get_svg()

    r = c.put(f"/api/project/layout/pid/{first_eq}", json={"x": 500.0, "y": 60.0})
    assert r.status_code == 200

    moved = _get_svg()
    assert moved != base
    root = ET.fromstring(moved)
    rect = next(el for el in root.iter() if _local(el.tag) == "rect" and el.get("data-tag") == first_eq)
    assert float(rect.get("x", "0")) == 500.0
    assert float(rect.get("y", "0")) == 60.0


def test_pid_svg_ignores_unknown_placed_tag() -> None:
    """Placement overrides for tags with no equipment are a no-op."""
    _reset()
    base = _get_svg()
    assert c.put("/api/project/layout/pid/XX-9999", json={"x": 1.0, "y": 2.0}).status_code == 200
    assert _get_svg() == base
