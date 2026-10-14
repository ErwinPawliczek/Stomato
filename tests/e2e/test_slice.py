"""THE DEMO. Slice flowsheet end to end. xfail until every layer lands; the final spec removes xfail."""

import xml.etree.ElementTree as ET

import pytest

from ngdesign import registry
from ngdesign.flowsheets import slice as slice_fs


@pytest.mark.slice
def test_slice_end_to_end():
    thermo = registry.create("thermo", "pr")
    solved = registry.create("solver", "sequential_modular").solve(slice_fs.build(), thermo)
    assert solved.converged
    pid = registry.create("pid_builder", "default").build(solved)
    for _ in range(5):
        before = pid.model_dump()
        for name in registry.available("pid_rule"):
            pid = registry.create("pid_rule", name).apply(pid)
        if pid.model_dump() == before:
            break
    pfd_svg = registry.create("diagram", "pfd").render(solved)
    pid_svg = registry.create("diagram", "pid").render(pid)
    ET.fromstring(pfd_svg)
    ET.fromstring(pid_svg)
    net = registry.create("router", "orthogonal").route(pid, layout={})
    iso = registry.create("iso_renderer", "svg")
    sheets = [iso.render(line, pid) for line in net.lines]
    assert len(sheets) >= 5
    for s in sheets:
        ET.fromstring(s.svg)
