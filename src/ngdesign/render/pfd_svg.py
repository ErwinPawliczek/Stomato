"""PFD SVG renderer (spec S-22). Kind ``diagram``, name ``pfd``.

Renders a SolvedFlowsheet as a process flow diagram: major equipment
left to right in topological order of the Flowsheet, main streams as
orthogonal lines with arrows and stream-number diamonds, feeds entering
from the left, products leaving to the right, a stream table and an
equipment duty/power summary below. Pure function of the input —
deterministic output, no I/O, built with ``xml.etree`` only.

The P&ID renderer (spec S-18) owns the shared symbol library; until that
PR merges this module draws its own simple equipment shapes, per the
spec's "else draws its own" clause.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from ngdesign.contracts import (
    Flowsheet,
    SolvedFlowsheet,
    StreamState,
    UnitResult,
    UnitSpec,
)
from ngdesign.registry import register

SVG_NS = "http://www.w3.org/2000/svg"
STROKE = "#1a1a1a"

# Serialize with the SVG namespace as the default (no ns0: prefixes).
ET.register_namespace("", SVG_NS)

MARGIN = 40.0
H_GAP = 80.0
V_GAP = 60.0
ROW_H = 18.0  # stream-table row height
CHAR_W = 5.2  # rough average glyph width for sizing table columns

_Point = tuple[float, float]

# Local SVG primitives — S-22 draws its own symbols (S-18's shared library is
# a separate PR), so this module is self-contained by design.


def stroke_attrs(attrs: dict[str, str]) -> dict[str, str]:
    return {**attrs, "fill": "none", "stroke": STROKE, "stroke-width": "1.2"}


def new_svg(width: float, height: float) -> ET.Element:
    root = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": f"0 0 {_fmt(width)} {_fmt(height)}"})
    ET.SubElement(
        root,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": _fmt(width),
            "height": _fmt(height),
            "fill": "#ffffff",
            "stroke": "none",
        },
    )
    return root


def group(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, "g")


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _text(
    parent: ET.Element, x: float, y: float, s: str, size: float = 8.0, anchor: str = "middle"
) -> ET.Element:
    el = ET.SubElement(
        parent,
        "text",
        {"x": _fmt(x), "y": _fmt(y), "font-size": _fmt(size), "text-anchor": anchor, "fill": "#1a1a1a"},
    )
    el.text = s
    return el


def _polyline(parent: ET.Element, points: list[_Point]) -> None:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    ET.SubElement(parent, "polyline", stroke_attrs({"points": pts}))


def _polygon(parent: ET.Element, points: list[_Point]) -> None:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    ET.SubElement(parent, "polygon", stroke_attrs({"points": pts}))


# --------------------------------------------------------------------------
# Layout: units left to right by topological order of the Flowsheet
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Placement:
    tag: str
    cx: float
    cy: float
    w: float
    h: float


def _topological_layers(units: list[UnitSpec], flowsheet: Flowsheet) -> dict[str, int]:
    tags = [u.tag for u in units]
    succ: dict[str, set[str]] = {t: set() for t in tags}
    indeg: dict[str, int] = {t: 0 for t in tags}
    for s in flowsheet.streams:
        if s.source and s.target and s.source.unit != s.target.unit:
            if s.target.unit not in succ[s.source.unit]:
                succ[s.source.unit].add(s.target.unit)
                indeg[s.target.unit] += 1
    layer = {t: 0 for t in tags}
    queue = sorted(t for t in tags if indeg[t] == 0)
    done: set[str] = set()
    while queue:
        n = queue.pop(0)
        done.add(n)
        for m in sorted(succ[n]):
            layer[m] = max(layer[m], layer[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    max_layer = max(layer.values(), default=0)
    for t in tags:  # cycles park after the last layer
        if t not in done:
            layer[t] = max_layer + 1
    return layer


def _unit_size(kind: str) -> tuple[float, float]:
    k = kind.lower()
    if "pump" in k:
        return 50.0, 50.0
    if "compressor" in k:
        return 80.0, 60.0
    if "contactor" in k or "column" in k:
        return 60.0, 140.0
    if "separator" in k or "drum" in k or "vessel" in k:
        return 110.0, 90.0
    return 70.0, 70.0  # exchangers and anything else


def _layout(flowsheet: Flowsheet) -> dict[str, _Placement]:
    layers = _topological_layers(flowsheet.units, flowsheet)
    sizes = {u.tag: _unit_size(u.kind) for u in flowsheet.units}
    cell_w = max(sizes.values(), key=lambda s: s[0])[0] + H_GAP
    cell_h = max(sizes.values(), key=lambda s: s[1])[1] + V_GAP

    rows: dict[int, list[str]] = {}
    for u in flowsheet.units:
        rows.setdefault(layers[u.tag], []).append(u.tag)

    placements: dict[str, _Placement] = {}
    for col, members in sorted(rows.items()):
        for row, tag in enumerate(sorted(members)):
            w, h = sizes[tag]
            placements[tag] = _Placement(
                tag=tag,
                cx=MARGIN + col * cell_w + w / 2,
                cy=MARGIN + row * cell_h + h / 2,
                w=w,
                h=h,
            )
    return placements


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


def _draw_unit(parent: ET.Element, kind: str, p: _Placement) -> None:
    """Major-equipment symbols; the P&ID renderer's shared library draws the rich set."""
    cx, cy, w, h = p.cx, p.cy, p.w, p.h
    k = kind.lower()
    if "pump" in k:
        _polygon(parent, [(cx - w / 2, cy - h / 4), (cx - w / 2, cy + h / 4), (cx + w / 2, cy)])
    elif "compressor" in k:
        _polygon(
            parent,
            [
                (cx - w / 2, cy - h / 2),
                (cx + w / 2, cy - h / 4),
                (cx + w / 2, cy + h / 4),
                (cx - w / 2, cy + h / 2),
            ],
        )
    elif "contactor" in k or "column" in k:
        ET.SubElement(
            parent,
            "rect",
            stroke_attrs({"x": _fmt(cx - w / 2), "y": _fmt(cy - h / 2), "width": _fmt(w), "height": _fmt(h)}),
        )
    elif "separator" in k or "drum" in k or "vessel" in k:
        ET.SubElement(
            parent,
            "rect",
            stroke_attrs(
                {
                    "x": _fmt(cx - w / 2),
                    "y": _fmt(cy - h / 2),
                    "width": _fmt(w),
                    "height": _fmt(h),
                    "rx": _fmt(h / 4),
                }
            ),
        )
    else:  # exchangers: circle with a zigzag
        r = min(w, h) / 2
        ET.SubElement(parent, "circle", stroke_attrs({"cx": _fmt(cx), "cy": _fmt(cy), "r": _fmt(r)}))
        span = w * 0.6
        step = span / 4
        pts: list[_Point] = [(cx - span / 2, cy)]
        for i in range(4):
            pts.append((cx - span / 2 + step * (i + 0.5), cy - r / 2.5 if i % 2 == 0 else cy + r / 2.5))
        pts.append((cx + span / 2, cy))
        _polyline(parent, pts)


def _route_stream(source_pt: _Point, target_pt: _Point) -> list[_Point]:
    """Orthogonal run: out of the source's right edge, into the target's left edge."""
    x1, y1 = source_pt
    x2, y2 = target_pt
    mid_x = (x1 + x2) / 2
    if y1 == y2:
        return [source_pt, target_pt]
    return [source_pt, (mid_x, y1), (mid_x, y2), target_pt]


def _arrow_head(parent: ET.Element, tail: _Point, tip: _Point) -> None:
    tx, ty = tip
    ax, ay = tail
    head = 7.0
    if tx != ax:
        sign = 1.0 if tx >= ax else -1.0
        _polygon(parent, [(tx - head * sign, ty - head / 2), (tx - head * sign, ty + head / 2), (tx, ty)])
    else:
        sign = 1.0 if ty >= ay else -1.0
        _polygon(parent, [(tx - head / 2, ty - head * sign), (tx + head / 2, ty - head * sign), (tx, ty)])


def _diamond(parent: ET.Element, cx: float, cy: float, s: float) -> None:
    _polygon(parent, [(cx, cy - s / 2), (cx + s / 2, cy), (cx, cy + s / 2), (cx - s / 2, cy)])


def _draw_stream(parent: ET.Element, stream_id: str, points: list[_Point]) -> None:
    _polyline(parent, points)
    _arrow_head(parent, points[-2], points[-1])
    # Stream-number diamond at the middle of the run, id text just above it.
    total = sum(
        abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    )
    remaining = total / 2
    x, y = points[0]
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        seg = abs(x2 - x1) + abs(y2 - y1)
        if seg > 0 and remaining <= seg:
            t = remaining / seg
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            break
        remaining -= seg
    _diamond(parent, x, y, 12.0)
    _text(parent, x, y - 10, stream_id, size=7.0)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def _stream_row(state: StreamState | None) -> list[str]:
    if state is None:
        return ["—"] * 6
    try:
        mass_kg_h = f"{state.mass_flow * 3600:.0f}"
    except ValueError:
        mass_kg_h = "—"  # no phases: mass flow needs the thermo layer
    return [
        f"{state.T - 273.15:.1f}",
        f"{state.P / 1000.0 - 101.325:.1f}",
        f"{state.molar_flow * 3600.0 / 1000.0:.2f}",
        mass_kg_h,
        f"{state.vapor_fraction:.2f}",
    ]


def _draw_table(
    parent: ET.Element,
    x: float,
    y: float,
    headers: list[str],
    rows: list[tuple[str, list[str]]],
    first_col: str,
) -> float:
    """Simple gridded table; returns the y below the last row."""
    col_w = max(60.0, max(len(h) for h in headers) * CHAR_W + 12.0)
    _text(parent, x, y, first_col, size=9.0)
    y += 6.0
    header_row = [first_col, *headers]
    xs = [x + i * col_w for i in range(len(header_row))]
    for i, htxt in enumerate(header_row):
        _text(parent, xs[i] + col_w / 2, y + 10, htxt, size=7.5)
    ET.SubElement(
        parent,
        "line",
        stroke_attrs(
            {"x1": _fmt(x), "y1": _fmt(y + 14), "x2": _fmt(x + len(header_row) * col_w), "y2": _fmt(y + 14)}
        ),
    )
    yy = y + 14
    for row in rows:
        g = ET.SubElement(parent, "g", {"class": "table-row", "data-row": row[0]})
        yy += ROW_H
        for c_i, cell in enumerate([row[0], *row[1]]):
            _text(g, xs[c_i] + col_w / 2, yy - 4, cell, size=7.5)
    return yy


# --------------------------------------------------------------------------
# Plugin
# --------------------------------------------------------------------------


def render_pfd_svg(solved: SolvedFlowsheet) -> str:
    """Render a SolvedFlowsheet to a complete SVG document string."""
    flowsheet = solved.flowsheet
    placements = _layout(flowsheet)

    max_x = max((p.cx + p.w / 2 for p in placements.values()), default=0.0)
    max_y = max((p.cy + p.h / 2 for p in placements.values()), default=0.0)
    diagram_w = max_x + MARGIN + 60.0
    table_y = max_y + MARGIN + 30.0

    headers = ["T (C)", "P (kPa g)", "kmol/h", "kg/h", "Vf"]
    stream_rows: list[tuple[str, list[str]]] = []
    for s in flowsheet.streams:
        stream_rows.append((s.id, _stream_row(solved.streams.get(s.id))))
    unit_rows: list[tuple[str, list[str]]] = []
    for u in flowsheet.units:
        r: UnitResult | None = solved.units.get(u.tag)
        unit_rows.append(
            (
                u.tag,
                [
                    "—" if r is None else f"{r.duty_W / 1000.0:.1f}",
                    "—" if r is None else f"{r.power_W / 1000.0:.1f}",
                ],
            )
        )
    n_rows = len(stream_rows) + len(unit_rows) + 6
    height = table_y + n_rows * ROW_H + 60.0

    root = new_svg(diagram_w, height)
    stream_layer = group(root)
    unit_layer = group(root)
    table_layer = group(root)

    # Streams first; equipment draws on top.
    for s in flowsheet.streams:
        if s.source and s.target and s.source.unit in placements and s.target.unit in placements:
            src = placements[s.source.unit]
            tgt = placements[s.target.unit]
            points = _route_stream((src.cx + src.w / 2, src.cy), (tgt.cx - tgt.w / 2, tgt.cy))
        elif s.target:  # feed: enters from the left edge
            tgt = placements[s.target.unit]
            points = _route_stream((2.0, tgt.cy), (tgt.cx - tgt.w / 2, tgt.cy))
        elif s.source:  # product: leaves to the right edge
            src = placements[s.source.unit]
            points = _route_stream((src.cx + src.w / 2, src.cy), (diagram_w - 2.0, src.cy))
        else:
            continue
        _draw_stream(stream_layer, s.id, points)

    for u in flowsheet.units:
        p = placements[u.tag]
        _draw_unit(unit_layer, u.kind, p)
        _text(unit_layer, p.cx, p.cy - p.h / 2 - 5, u.tag, size=9.0)

    after_streams = _draw_table(
        table_layer, MARGIN, table_y, headers, [(sid, cells) for sid, cells in stream_rows], "Stream"
    )
    _draw_table(table_layer, MARGIN, after_streams + 20.0, ["duty (kW)", "power (kW)"], unit_rows, "Unit")

    return ET.tostring(root, encoding="unicode")


@register("diagram", "pfd")
class PfdSvgRenderer:
    """Kind ``diagram``, name ``pfd``: renders a :class:`SolvedFlowsheet` to SVG."""

    def render(self, obj: Any) -> str:
        if not isinstance(obj, SolvedFlowsheet):
            raise TypeError(f"pfd renderer expects a SolvedFlowsheet, got {type(obj).__name__}")
        return render_pfd_svg(obj)
