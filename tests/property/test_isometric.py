"""Isometric invariants on the sample routed line. LOCKED."""

import math
import xml.etree.ElementTree as ET

import pytest

from ngdesign import registry
from ngdesign.contracts import ComponentKind
from ngdesign.flowsheets.samples import sample_pid, sample_routed_line


@pytest.fixture
def renderer():
    names = registry.available("iso_renderer")
    if not names:
        pytest.skip("no iso renderer yet")
    return registry.create("iso_renderer", names[0])


def test_iso_invariants(renderer):
    line = sample_routed_line()
    sheet = renderer.render(line, sample_pid())
    ET.fromstring(sheet.svg)  # well-formed SVG
    pipe_len = sum(c.length_mm for c in line.components if c.kind == ComponentKind.PIPE)
    assert math.isclose(sheet.total_pipe_length_mm, pipe_len, rel_tol=1e-9)
    assert math.isclose(sum(p.length_mm for p in sheet.cut_list), pipe_len, rel_tol=1e-6)
    n_elbows = sum(1 for c in line.components if c.kind == ComponentKind.ELBOW_90_LR)
    bom_elbows = sum(b.qty for b in sheet.bom if "elbow" in b.description.lower())
    assert bom_elbows == n_elbows
    assert sheet.weld_count == len(line.components) - 1 - sum(
        1
        for a, b in zip(line.components, line.components[1:], strict=False)
        if a.end_types[1].value == "fl" and b.end_types[0].value == "fl"
    )
    assert sheet.title.line_number == line.line_number
