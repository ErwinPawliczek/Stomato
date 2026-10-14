"""Tests for the S-19 isometric SVG renderer (kind iso_renderer, name svg)."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from ngdesign import data, registry
from ngdesign.contracts import (
    Component,
    ComponentKind,
    EndType,
    RoutedLine,
    Vec3,
)
from ngdesign.flowsheets.samples import sample_pid, sample_routed_line

ATM_PA = 101_325.0


@pytest.fixture(name="sheet")
def _sheet():
    renderer = registry.create("iso_renderer", "svg")
    return renderer.render(sample_routed_line(), sample_pid())


def test_every_pipe_run_dimension_appears(sheet) -> None:
    """Acceptance: each straight run's centre-to-centre length is dimensioned."""
    for c in sample_routed_line().components:
        if c.kind == ComponentKind.PIPE:
            assert f"{c.length_mm:.1f}" in sheet.svg


def test_svg_is_well_formed_with_expected_marks(sheet) -> None:
    root = ET.fromstring(sheet.svg)
    assert root.tag.endswith("svg")
    assert sheet.svg.count("<circle") == 6  # weld dots: 7 components -> 6 joints
    assert sheet.svg.count("<polygon") == 2  # flow arrow + north arrowhead
    assert ">N<" in sheet.svg  # north arrow label
    assert '6"-PG-1003-D1' in sheet.svg  # title block line number


def test_title_block_uses_matching_pid_line(sheet) -> None:
    pid_line = next(ln for ln in sample_pid().lines if ln.number == '6"-PG-1003-D1')
    design_kpag = (pid_line.design_pressure_Pa - ATM_PA) / 1000.0
    assert sheet.title.line_number == pid_line.number
    assert sheet.title.pipe_class == pid_line.pipe_class
    assert sheet.title.design_pressure_kPag == pytest.approx(design_kpag)
    assert sheet.title.design_temperature_C == pytest.approx(pid_line.design_temperature_K - 273.15)
    assert sheet.title.test_pressure_kPag == pytest.approx(1.5 * design_kpag)


def test_bom_groups_identical_descriptions(sheet) -> None:
    assert [b.item for b in sheet.bom] == [1, 2, 3]
    flanges, pipes, elbows = sheet.bom
    assert flanges.description == '6" WN flange cl600 RTJ'
    assert flanges.qty == 2.0 and flanges.unit == "ea"
    assert pipes.description == '6" pipe SCH80'
    assert pipes.unit == "m"
    assert pipes.qty == pytest.approx(5.3856, rel=1e-9)
    assert elbows.description == '6" 90 LR elbow SCH80'
    assert elbows.qty == 2.0 and elbows.unit == "ea"
    material = data.pipe_classes()["D1"]["material"]
    assert all(b.material == material for b in sheet.bom)


def test_cut_list_one_piece_per_pipe(sheet) -> None:
    pipes = [c for c in sample_routed_line().components if c.kind == ComponentKind.PIPE]
    assert [p.piece for p in sheet.cut_list] == [1, 2, 3]
    assert all(p.spool == "SP-1" for p in sheet.cut_list)
    assert [p.length_mm for p in sheet.cut_list] == [pytest.approx(c.length_mm, rel=1e-9) for c in pipes]
    assert all(p.nps_in == 6.0 for p in sheet.cut_list)


def test_totals_match_3d_model(sheet) -> None:
    line = sample_routed_line()
    pipe_len = sum(c.length_mm for c in line.components if c.kind == ComponentKind.PIPE)
    assert math.isclose(sheet.total_pipe_length_mm, pipe_len, rel_tol=1e-9)
    assert math.isclose(sum(p.length_mm for p in sheet.cut_list), pipe_len, rel_tol=1e-6)
    assert sheet.weld_count == 6


def _flange_to_flange_line() -> RoutedLine:
    """Two butt-welded-together flanges: the joint is flange-to-flange, no weld."""
    common = dict(nps_in=6.0, pipe_class="D1")
    return RoutedLine(
        line_number='9"-XX-9999-Z9',
        components=[
            Component(
                id="F1",
                kind=ComponentKind.FLANGE_WN,
                start=Vec3(x=0, y=0, z=0),
                end=Vec3(x=100, y=0, z=0),
                end_types=(EndType.BUTT_WELD, EndType.FLANGED),
                description='6" WN flange cl600 RTJ',
                **common,
            ),
            Component(
                id="F2",
                kind=ComponentKind.FLANGE_WN,
                start=Vec3(x=100, y=0, z=0),
                end=Vec3(x=200, y=0, z=0),
                end_types=(EndType.FLANGED, EndType.BUTT_WELD),
                description='6" WN flange cl600 RTJ',
                **common,
            ),
        ],
    )


def test_flange_to_flange_joint_has_no_weld_and_title_falls_back() -> None:
    line = _flange_to_flange_line()
    renderer = registry.create("iso_renderer", "svg")
    sheet = renderer.render(line, sample_pid())
    assert sheet.weld_count == 0
    assert sheet.svg.count("<circle") == 0
    # No matching PidLine: pipe class comes from the components, conditions default to 0.
    assert sheet.title.pipe_class == "D1"
    assert sheet.title.design_pressure_kPag == 0.0
    assert sheet.title.test_pressure_kPag == 0.0
    ET.fromstring(sheet.svg)
