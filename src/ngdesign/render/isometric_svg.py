"""S-19: isometric SVG renderer — one RoutedLine as a fabrication isometric.

Plugin: kind "iso_renderer", name "svg".

Projection (screen y down): x' = (x - y) * cos30, y' = -(z + (x + y) * sin30).
Every axis-aligned unit vector projects to unit length under this mapping, so
projected run lengths equal 3D run lengths.

Centreline single-line style: pipe runs as lines (one mm dimension per run),
elbows as quadratic bend paths, flanges as double ticks, valves as bowties,
weld dots at every butt/socket-weld joint (flange-to-flange joints excluded),
flow arrow on the first pipe, north arrow, title block, BOM and cut list.

Pressure convention: contracts store Pa absolute; drawings report gauge kPag
(absolute - 101325 Pa). Hydrotest pressure = 1.5 x design gauge pressure.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from ngdesign import data
from ngdesign.contracts import (
    PID,
    BomItem,
    Component,
    ComponentKind,
    CutPiece,
    EndType,
    IsoSheet,
    RoutedLine,
    TitleBlock,
    Vec3,
)
from ngdesign.registry import register

COS30 = math.cos(math.radians(30.0))
SIN30 = 0.5
ATM_PA = 101_325.0
LINE_STROKE = "#1a1a1a"
FLOW_FILL = "#c62828"
WELD_RADIUS = 4.0
TICK_HALF = 9.0
DIM_OFFSET = 20.0
FRAME_PAD = 150.0

_BEND_KINDS = (
    ComponentKind.ELBOW_90_LR,
    ComponentKind.ELBOW_90_SR,
    ComponentKind.ELBOW_45_LR,
)
_FLANGE_KINDS = (ComponentKind.FLANGE_WN, ComponentKind.FLANGE_BLIND)


def _project(p: Vec3) -> tuple[float, float]:
    """Isometric projection: x' = (x - y) * cos30, y' = -(z + (x + y) * sin30)."""
    return (p.x - p.y) * COS30, -(p.z + (p.x + p.y) * SIN30)


class _Frame:
    """Shifts projected coordinates into a positive viewBox with a margin."""

    def __init__(self, points: list[Vec3], pad: float = FRAME_PAD) -> None:
        pts = [_project(p) for p in points] or [(0.0, 0.0)]
        self.x0 = min(x for x, _ in pts) - pad
        self.y0 = min(y for _, y in pts) - pad
        self.w = max(x for x, _ in pts) + pad - self.x0
        self.h = max(y for _, y in pts) + pad - self.y0

    def xy(self, p: Vec3) -> tuple[float, float]:
        x, y = _project(p)
        return x - self.x0, y - self.y0


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def _text(
    x: float,
    y: float,
    content: str,
    size: float = 14.0,
    anchor: str = "middle",
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{_fmt(x)}" y="{_fmt(y)}" font-family="ui-monospace, monospace" '
        f'font-size="{size:.0f}" font-weight="{weight}" text-anchor="{anchor}">'
        f"{escape(content)}</text>"
    )


def _seg(f: _Frame, a: Vec3, b: Vec3, width: float = 2.0) -> str:
    ax, ay = f.xy(a)
    bx, by = f.xy(b)
    return (
        f'<line x1="{_fmt(ax)}" y1="{_fmt(ay)}" x2="{_fmt(bx)}" y2="{_fmt(by)}" '
        f'stroke="{LINE_STROKE}" stroke-width="{width}" />'
    )


def _elbow_path(f: _Frame, c: Component) -> str:
    """Bend as a sampled quadratic curve rendered as a chain of line segments.

    Plain <line> elements render in every SVG consumer (curve shorthand and
    polyline do not), so the arc is discretised into short straight strokes.
    """
    if c.center is None:
        return _seg(f, c.start, c.end)
    sx, sy = f.xy(c.start)
    ex, ey = f.xy(c.end)
    cx, cy = f.xy(c.center)
    n = 12
    tvals = [i / n for i in range(n + 1)]
    pts = [
        (
            (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * ex,
            (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ey,
        )
        for t in tvals
    ]
    stroke = f'stroke="{LINE_STROKE}" stroke-width="2"'
    return "".join(
        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" {stroke} />'
        for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False)
    )


def _flange_ticks(f: _Frame, c: Component) -> str:
    """Double perpendicular ticks across the flange body."""
    ax, ay = f.xy(c.start)
    bx, by = f.xy(c.end)
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n == 0.0:
        return ""
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    parts: list[str] = []
    for t in (0.3, 0.7):
        mx, my = ax + dx * t, ay + dy * t
        parts.append(
            f'<line x1="{_fmt(mx + px * TICK_HALF)}" y1="{_fmt(my + py * TICK_HALF)}" '
            f'x2="{_fmt(mx - px * TICK_HALF)}" y2="{_fmt(my - py * TICK_HALF)}" '
            f'stroke="{LINE_STROKE}" stroke-width="3" />'
        )
    return "".join(parts)


def _valve_bowtie(f: _Frame, c: Component) -> str:
    ax, ay = f.xy(c.start)
    bx, by = f.xy(c.end)
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n == 0.0:
        return ""
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    l1x, l1y = mx - ux * 12.0, my - uy * 12.0
    l2x, l2y = mx + ux * 12.0, my + uy * 12.0
    tx, ty = mx + px * 9.0, my + py * 9.0
    bx2, by2 = mx - px * 9.0, my - py * 9.0
    fill = f'fill="white" stroke="{LINE_STROKE}" stroke-width="1.5"'
    return (
        f'<polygon points="{_fmt(l1x)},{_fmt(l1y)} {_fmt(tx)},{_fmt(ty)} {_fmt(bx2)},{_fmt(by2)}" {fill} />'
        f'<polygon points="{_fmt(l2x)},{_fmt(l2y)} {_fmt(tx)},{_fmt(ty)} {_fmt(bx2)},{_fmt(by2)}" {fill} />'
    )


def _draw_component(f: _Frame, c: Component) -> str:
    if c.kind in _BEND_KINDS:
        return _elbow_path(f, c)
    if c.kind in _FLANGE_KINDS:
        return _seg(f, c.start, c.end) + _flange_ticks(f, c)
    if c.kind == ComponentKind.VALVE:
        return _seg(f, c.start, c.end) + _valve_bowtie(f, c)
    return _seg(f, c.start, c.end)


def _is_flange_joint(a: Component, b: Component) -> bool:
    return a.end_types[1] == EndType.FLANGED and b.end_types[0] == EndType.FLANGED


def _weld_joints(line: RoutedLine) -> list[Vec3]:
    """Joint point at every consecutive pair except flange-to-flange."""
    return [
        a.end
        for a, b in zip(line.components, line.components[1:], strict=False)
        if not _is_flange_joint(a, b)
    ]


def _weld_dots(f: _Frame, line: RoutedLine) -> str:
    parts = []
    for j in _weld_joints(line):
        x, y = f.xy(j)
        parts.append(f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{WELD_RADIUS}" fill="{LINE_STROKE}" />')
    return "".join(parts)


def _first_pipe(line: RoutedLine) -> Component | None:
    return next((c for c in line.components if c.kind == ComponentKind.PIPE), None)


def _flow_arrow(f: _Frame, c: Component) -> str:
    ax, ay = f.xy(c.start)
    bx, by = f.xy(c.end)
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n == 0.0:
        return ""
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    tip = (mx + ux * 14.0, my + uy * 14.0)
    b1 = (mx - ux * 8.0 + px * 8.0, my - uy * 8.0 + py * 8.0)
    b2 = (mx - ux * 8.0 - px * 8.0, my - uy * 8.0 - py * 8.0)
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in (tip, b1, b2))
    return f'<polygon points="{pts}" fill="{FLOW_FILL}" />'


def _dimension(f: _Frame, c: Component) -> str:
    """Centre-to-centre length of one straight run in mm, labelled at the run.

    Text carries no transform: untransformed text renders identically in every
    SVG consumer, keeping the dimension legible in rasterised previews too.
    """
    ax, ay = f.xy(c.start)
    bx, by = f.xy(c.end)
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    if n == 0.0:
        return ""
    px, py = -dy / n, dx / n
    tx, ty = (ax + bx) / 2.0 + px * DIM_OFFSET, (ay + by) / 2.0 + py * DIM_OFFSET
    return _text(tx, ty, f"{c.length_mm:.1f}", size=13)


def _north_arrow(f: _Frame) -> str:
    """North (+y) projects to (-cos30, -sin30): up-left at 30 degrees."""
    ux, uy = -COS30, -SIN30
    ax, ay = f.w - 50.0, 70.0
    bx, by = ax + ux * 60.0, ay + uy * 60.0
    px, py = -uy, ux
    tip = (bx + ux * 14.0, by + uy * 14.0)
    b1 = (bx + px * 7.0, by + py * 7.0)
    b2 = (bx - px * 7.0, by - py * 7.0)
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in (tip, b1, b2))
    return (
        f'<line x1="{_fmt(ax)}" y1="{_fmt(ay)}" x2="{_fmt(bx)}" y2="{_fmt(by)}" '
        f'stroke="{LINE_STROKE}" stroke-width="2" />'
        f'<polygon points="{pts}" fill="{LINE_STROKE}" />'
        + _text(ax + 16.0, ay + 6.0, "N", size=16, anchor="start", weight="bold")
    )


def _title_block(f: _Frame, t: TitleBlock) -> str:
    x, y = f.w - 350.0, f.h - 165.0
    rect = (
        f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="330" height="145" '
        f'fill="white" stroke="{LINE_STROKE}" stroke-width="1.5" />'
    )
    rows = [
        f"ISOMETRIC  {t.line_number}",
        f"Pipe class: {t.pipe_class}",
        f"Design: {t.design_pressure_kPag:.1f} kPag / {t.design_temperature_C:.1f} C",
        f"Hydrotest: {t.test_pressure_kPag:.1f} kPag",
        f"Insulation: {t.insulation}",
        f"Sheet: {t.sheet}",
    ]
    texts = "".join(
        _text(x + 12.0, y + 26.0 + i * 22.0, row, size=13, anchor="start") for i, row in enumerate(rows)
    )
    return rect + texts


def _bom_table(f: _Frame, bom: list[BomItem]) -> str:
    parts = [_text(24.0, 36.0, "BILL OF MATERIAL", size=14, anchor="start", weight="bold")]
    for b in bom:
        qty = f"{b.qty:.2f}" if b.unit == "m" else f"{b.qty:.0f}"
        row = f"{b.item}.  {b.description}  -  {qty} {b.unit}"
        parts.append(_text(24.0, 36.0 + 24.0 * b.item, row, size=12, anchor="start"))
    return "".join(parts)


def _title(line: RoutedLine, pid: PID) -> TitleBlock:
    """TitleBlock from the matching PidLine; fall back to the RoutedLine."""
    pid_line = next((ln for ln in pid.lines if ln.number == line.line_number), None)
    if pid_line is None:
        pipe_class = line.components[0].pipe_class if line.components else ""
        design_kpag = 0.0
        design_c = 0.0
    else:
        pipe_class = pid_line.pipe_class
        design_kpag = (pid_line.design_pressure_Pa - ATM_PA) / 1000.0
        design_c = pid_line.design_temperature_K - 273.15
    return TitleBlock(
        line_number=line.line_number,
        pipe_class=pipe_class,
        design_pressure_kPag=design_kpag,
        design_temperature_C=design_c,
        test_pressure_kPag=1.5 * design_kpag,
    )


def _material(pipe_class: str) -> str:
    return str(data.pipe_classes().get(pipe_class, {}).get("material", ""))


def _bom(line: RoutedLine, material: str) -> list[BomItem]:
    """Identical descriptions grouped; pipe quantity in metres, fittings in ea."""
    order: list[str] = []
    qty: dict[str, float] = {}
    nps: dict[str, float] = {}
    is_pipe: dict[str, bool] = {}
    for c in line.components:
        if c.description not in qty:
            order.append(c.description)
            qty[c.description] = 0.0
            nps[c.description] = c.nps_in
            is_pipe[c.description] = c.kind == ComponentKind.PIPE
        if is_pipe[c.description]:
            qty[c.description] += c.length_mm / 1000.0
        else:
            qty[c.description] += 1.0
    return [
        BomItem(
            item=i + 1,
            qty=qty[d],
            unit="m" if is_pipe[d] else "ea",
            nps_in=nps[d],
            description=d,
            material=material,
        )
        for i, d in enumerate(order)
    ]


def _cut_list(line: RoutedLine) -> list[CutPiece]:
    """One cut piece per PIPE component; spool 'SP-1' until spool breaks exist."""
    return [
        CutPiece(piece=i + 1, spool="SP-1", nps_in=c.nps_in, length_mm=c.length_mm)
        for i, c in enumerate(c for c in line.components if c.kind == ComponentKind.PIPE)
    ]


def _svg(line: RoutedLine, title: TitleBlock, bom: list[BomItem]) -> str:
    points: list[Vec3] = []
    for c in line.components:
        points.extend((c.start, c.end))
        if c.center is not None:
            points.append(c.center)
    f = _Frame(points)
    parts: list[str] = [f'<rect x="0" y="0" width="{_fmt(f.w)}" height="{_fmt(f.h)}" fill="white" />']
    for c in line.components:
        parts.append(_draw_component(f, c))
    parts.append(_weld_dots(f, line))
    first = _first_pipe(line)
    if first is not None:
        parts.append(_flow_arrow(f, first))
    for c in line.components:
        if c.kind == ComponentKind.PIPE:
            parts.append(_dimension(f, c))
    parts.append(_north_arrow(f))
    parts.append(_title_block(f, title))
    parts.append(_bom_table(f, bom))
    body = "".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(f.w)} {_fmt(f.h)}" '
        f'width="{f.w:.0f}" height="{f.h:.0f}">{body}</svg>'
    )


@register("iso_renderer", "svg")
class SvgIsoRenderer:
    """Fabrication isometric for one RoutedLine (spec S-19)."""

    def render(self, line: RoutedLine, pid: PID) -> IsoSheet:
        title = _title(line, pid)
        bom = _bom(line, _material(title.pipe_class))
        return IsoSheet(
            title=title,
            svg=_svg(line, title, bom),
            bom=bom,
            cut_list=_cut_list(line),
            weld_count=len(_weld_joints(line)),
            total_pipe_length_mm=sum(c.length_mm for c in line.components if c.kind == ComponentKind.PIPE),
        )
