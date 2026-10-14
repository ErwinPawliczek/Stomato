"""Tests for the S-22 PFD SVG renderer."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from ngdesign.contracts import Phase, PhaseKind, SolvedFlowsheet, StreamState, UnitResult
from ngdesign.flowsheets.slice import build
from ngdesign.render.pfd_svg import render_pfd_svg

SVG_NS = "http://www.w3.org/2000/svg"


def _phase(kind: PhaseKind, fraction: float, mw: float) -> Phase:
    return Phase(
        kind=kind, mole_fraction=fraction, composition={"C1": 1.0}, density=40.0, molecular_weight=mw
    )


def _state(T: float, P: float, molar_flow: float, vapor_fraction: float) -> StreamState:
    """Hand-made plausible StreamState — no thermo needed."""
    phases: list[Phase] = []
    if vapor_fraction > 0:
        phases.append(_phase(PhaseKind.VAPOR, vapor_fraction, 18.5))
    if vapor_fraction < 1:
        phases.append(_phase(PhaseKind.HC_LIQUID, 1.0 - vapor_fraction, 62.0))
    return StreamState(
        T=T,
        P=P,
        molar_flow=molar_flow,
        composition={"C1": 1.0},
        vapor_fraction=vapor_fraction,
        enthalpy=-1.0e4,
        entropy=80.0,
        phases=phases,
    )


def _solved_slice() -> SolvedFlowsheet:
    flowsheet = build()
    streams = {
        s.id: _state(
            T=300.0 + 20.0 * i, P=3.5e6 + 1.0e5 * i, molar_flow=280.0 - 10.0 * i, vapor_fraction=(i % 3) / 2.0
        )
        for i, s in enumerate(flowsheet.streams)
    }
    units = {
        u.tag: UnitResult(outlets={}, duty_W=1.0e5 * i, power_W=5.0e4 * i)
        for i, u in enumerate(flowsheet.units)
    }
    return SolvedFlowsheet(flowsheet=flowsheet, streams=streams, units=units, converged=True)


def _text_contents(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return [el.text for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "text" and el.text]


def test_registered_as_diagram_pfd() -> None:
    from ngdesign.registry import available, create

    assert "pfd" in available("diagram")
    renderer = create("diagram", "pfd")
    assert callable(renderer.render)


def test_render_wellformed_svg() -> None:
    svg = render_pfd_svg(_solved_slice())
    root = ET.fromstring(svg)  # raises if not well-formed XML
    assert root.tag == f"{{{SVG_NS}}}svg"


def test_every_unit_tag_and_stream_id_appears_as_text() -> None:
    solved = _solved_slice()
    texts = set(_text_contents(render_pfd_svg(solved)))
    for u in solved.flowsheet.units:
        assert u.tag in texts, f"unit tag {u.tag} missing"
    for s in solved.flowsheet.streams:
        assert s.id in texts, f"stream id {s.id} missing"


def test_stream_table_has_one_row_per_stream() -> None:
    solved = _solved_slice()
    root = ET.fromstring(render_pfd_svg(solved))
    rows = [
        el
        for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "g"
        and el.get("class") == "table-row"
        and (el.get("data-row") or "").startswith("S-")
    ]
    assert len(rows) == len(solved.flowsheet.streams)
    row_ids = {el.get("data-row") for el in rows}
    assert row_ids == {s.id for s in solved.flowsheet.streams}


def test_stream_table_carries_process_quantities() -> None:
    solved = _solved_slice()
    texts = set(_text_contents(render_pfd_svg(solved)))
    first = solved.flowsheet.streams[0]
    state = solved.streams[first.id]
    assert f"{state.T - 273.15:.1f}" in texts  # T in C
    assert f"{state.molar_flow * 3600.0 / 1000.0:.2f}" in texts  # kmol/h
    assert f"{state.mass_flow * 3600:.0f}" in texts  # kg/h (phases present)


def test_equipment_summary_row_duty_power() -> None:
    solved = _solved_slice()
    texts = set(_text_contents(render_pfd_svg(solved)))
    first_unit = solved.flowsheet.units[0]
    result = solved.units[first_unit.tag]
    assert f"{result.duty_W / 1000.0:.1f}" in texts
    assert f"{result.power_W / 1000.0:.1f}" in texts


def test_render_is_deterministic() -> None:
    solved = _solved_slice()
    assert render_pfd_svg(solved) == render_pfd_svg(solved)
