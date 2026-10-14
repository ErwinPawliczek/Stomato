"""P&ID SVG renderer (spec S-18). Kind ``diagram``, name ``pid``.

Layout: equipment placed left to right in topological order of the line
graph (edges from LineEnd links), lines drawn as orthogonal polylines
between nozzle anchor points, inline items drawn in flow order along the
line. Pure functions of the PID — deterministic output, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from xml.etree import ElementTree as ET

from ngdesign.contracts import (
    PID,
    XY,
    Direction,
    InlineKind,
    PidEquipment,
    PidLine,
    Valve,
)
from ngdesign.registry import register
from ngdesign.render import symbols as sym

#: mm (contract units for nozzle positions) -> SVG pixels
SCALE = 0.05
MARGIN = 40.0
H_GAP = 90.0
V_GAP = 70.0
STUB = 30.0
BOUNDARY_STUB = 70.0
BBOX_PAD_MM = 400.0

_Point = tuple[float, float]


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Placement:
    """Where an equipment sits: bbox rect and mm-origin point, in SVG px."""

    tag: str
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    origin_x: float  # SVG position of the equipment's mm origin (0, 0)
    origin_y: float


def _topological_layers(tags: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Longest-path layering via Kahn's algorithm; cycle leftovers go last."""
    succ: dict[str, set[str]] = {t: set() for t in tags}
    indeg: dict[str, int] = {t: 0 for t in tags}
    for u, v in edges:
        if v not in succ[u]:
            succ[u].add(v)
            indeg[v] += 1
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
    # Nodes caught in a cycle never reach indeg 0: park them after the last layer.
    max_layer = max(layer.values(), default=0)
    for t in tags:
        if t not in done:
            layer[t] = max_layer + 1
    return layer


def _equipment_bbox_mm(eq: PidEquipment) -> tuple[float, float, float, float]:
    """(min_x, max_x, min_z, max_z) over the nozzles plus padding."""
    xs = [0.0] + [n.position_mm.x for n in eq.nozzles]
    zs = [0.0] + [n.position_mm.z for n in eq.nozzles]
    pad = BBOX_PAD_MM
    return min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad


def _layout(pid: PID, placed: dict[str, XY] | None = None) -> dict[str, _Placement]:
    tags = sorted(e.tag for e in pid.equipment)
    by_tag = {e.tag: e for e in pid.equipment}
    edges = [
        (ln.start.equipment, ln.end.equipment)
        for ln in pid.lines
        if ln.start.equipment and ln.end.equipment and ln.start.equipment != ln.end.equipment
    ]
    layers = _topological_layers(tags, edges)

    spans = {t: _equipment_bbox_mm(by_tag[t]) for t in tags}
    widths = {t: (spans[t][1] - spans[t][0]) * SCALE for t in tags}
    heights = {t: (spans[t][3] - spans[t][2]) * SCALE for t in tags}
    cell_w = max(widths.values(), default=0.0) + H_GAP
    cell_h = max(heights.values(), default=0.0) + V_GAP

    placements: dict[str, _Placement] = {}
    rows: dict[int, list[str]] = {}
    for t in tags:
        rows.setdefault(layers[t], []).append(t)
    for col, members in sorted(rows.items()):
        for row, t in enumerate(sorted(members)):
            min_x, _max_x, min_z, max_z = spans[t]
            bx = MARGIN + col * cell_w
            by = MARGIN + row * cell_h
            placements[t] = _Placement(
                tag=t,
                bbox_x=bx,
                bbox_y=by,
                bbox_w=widths[t],
                bbox_h=heights[t],
                origin_x=bx - min_x * SCALE,
                origin_y=by + max_z * SCALE,
            )

    # User placements (view px, bbox top-left) win over the auto layout; the
    # equipment origin shifts by the same delta so nozzle geometry follows.
    for tag, pos in (placed or {}).items():
        p = placements.get(tag)
        if p is not None:
            dx, dy = pos.x - p.bbox_x, pos.y - p.bbox_y
            placements[tag] = replace(
                p, bbox_x=pos.x, bbox_y=pos.y, origin_x=p.origin_x + dx, origin_y=p.origin_y + dy
            )
    return placements


def _anchor(p: _Placement, equipment: PidEquipment, nozzle: str) -> tuple[_Point, Direction]:
    noz = next(n for n in equipment.nozzles if n.id == nozzle)
    pt = (p.origin_x + noz.position_mm.x * SCALE, p.origin_y - noz.position_mm.z * SCALE)
    return pt, noz.facing


# --------------------------------------------------------------------------
# Line routing
# --------------------------------------------------------------------------


def _unit_vector(d: Direction) -> _Point:
    return {
        Direction.E: (1.0, 0.0),
        Direction.W: (-1.0, 0.0),
        Direction.UP: (0.0, -1.0),
        Direction.N: (0.0, -1.0),
        Direction.DOWN: (0.0, 1.0),
        Direction.S: (0.0, 1.0),
    }[d]


def _add(a: _Point, d: _Point, dist: float) -> _Point:
    return (a[0] + d[0] * dist, a[1] + d[1] * dist)


def _opposite(d: _Point) -> _Point:
    return (-d[0], -d[1])


def _route(start: _Point, start_dir: _Point, end: _Point, end_dir: _Point) -> list[_Point]:
    """Orthogonal polyline from the start anchor to the end anchor.

    ``start_dir``/``end_dir`` point away from the respective anchor (the
    nozzle's facing, or towards the remote anchor at boundary ends).
    """
    a = _add(start, start_dir, STUB)
    b = _add(end, end_dir, STUB)
    if a[0] == b[0] or a[1] == b[1]:
        middle = [a, b]
    elif start_dir[0] != 0.0:
        middle = [a, (b[0], a[1]), b]
    else:
        middle = [a, (a[0], b[1]), b]
    return [start, *middle, end]


def _path_length(points: list[_Point]) -> float:
    return sum(
        abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    )


def _point_at(points: list[_Point], distance: float) -> tuple[float, float, float]:
    """Point at a polyline arc length, plus the segment angle in degrees."""
    remaining = distance
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        seg = abs(x2 - x1) + abs(y2 - y1)
        if seg > 0 and remaining <= seg:
            t = remaining / seg
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            angle = 0.0 if x2 != x1 else 90.0
            return x, y, angle
        remaining -= seg
    x, y = points[-1]
    return x, y, 0.0


def _point_at_fraction(points: list[_Point], fraction: float) -> tuple[float, float, float]:
    return _point_at(points, _path_length(points) * fraction)


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


def _draw_valve(parent: ET.Element, valve: Valve, x: float, y: float, angle: float = 0.0) -> None:
    g = sym.group(parent)
    g.set("data-tag", valve.tag)
    sym.valve_symbol(g, str(valve.type), x, y, angle)
    sym.add_text(g, x, y - sym.VALVE_SIZE / 2 - 4, valve.tag, size=7.0)


def _draw_inline_item(parent: ET.Element, item_kind: InlineKind, x: float, y: float, angle: float) -> None:
    if item_kind in (InlineKind.REDUCER_CONC, InlineKind.REDUCER_ECC):
        sym.reducer_symbol(parent, x, y, angle, eccentric=item_kind == InlineKind.REDUCER_ECC)
    elif item_kind == InlineKind.STRAINER:
        sym.strainer_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.ORIFICE:
        sym.orifice_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.SPEC_BREAK:
        sym.spec_break_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.BLIND:
        sym.spectacle_blind_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.INSTRUMENT_TAP:
        sym.instrument_tap_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.DRAIN:
        sym.drain_symbol(parent, x, y, angle)
    elif item_kind == InlineKind.VENT:
        sym.vent_symbol(parent, x, y, angle)
    else:  # InlineKind.VALVE is handled by the caller (needs the Valve model)
        raise ValueError(f"unhandled inline item kind {str(item_kind)!r}")


@dataclass(frozen=True)
class _LineGeometry:
    points: list[_Point]
    start_label: str | None
    end_label: str | None


def _line_geometry(line: PidLine, pid: PID, placements: dict[str, _Placement]) -> _LineGeometry:
    """Resolve the orthogonal polyline for one line plus boundary labels."""
    eq_by_tag = {e.tag: e for e in pid.equipment}

    def anchor_of(tag: str, noz: str) -> tuple[_Point, Direction]:
        return _anchor(placements[tag], eq_by_tag[tag], noz)

    s_eq = line.start.equipment
    e_eq = line.end.equipment
    if s_eq and e_eq:
        s, sd = anchor_of(s_eq, line.start.nozzle or "")
        e, ed = anchor_of(e_eq, line.end.nozzle or "")
        return _LineGeometry(_route(s, _unit_vector(sd), e, _unit_vector(ed)), None, None)

    if s_eq and not e_eq:
        s, sd = anchor_of(s_eq, line.start.nozzle or "")
        d = _unit_vector(sd)
        e = _add(s, d, BOUNDARY_STUB * 2)
        return _LineGeometry(_route(s, d, e, d), None, line.end.boundary)

    if e_eq and not s_eq:
        e, ed = anchor_of(e_eq, line.end.nozzle or "")
        d = _unit_vector(ed)
        s = _add(e, d, BOUNDARY_STUB * 2)  # approach the equipment from outside
        return _LineGeometry(_route(s, _opposite(d), e, d), line.start.boundary, None)

    # Both ends boundary (tie-in line): draw a horizontal run at the top.
    y = MARGIN / 2
    s = (MARGIN, y)
    e = (MARGIN + BOUNDARY_STUB * 2, y)
    return _LineGeometry(_route(s, (1.0, 0.0), e, (-1.0, 0.0)), line.start.boundary, line.end.boundary)


def _draw_line(
    parent: ET.Element, line: PidLine, pid: PID, placements: dict[str, _Placement]
) -> list[_Point]:
    """Draw one line's run, arrow head, labels; returns its polyline points."""
    geom = _line_geometry(line, pid, placements)
    points = geom.points
    g = sym.group(parent)
    g.set("data-tag", line.number)
    sym.add_polyline(g, points)

    # Arrow head at the flow end.
    (ax, ay), (bx, by) = points[-2], points[-1]
    head = 6.0
    if bx != ax:  # horizontal final segment
        sign = 1.0 if bx >= ax else -1.0
        tip = [(bx - head * sign, by - head / 2), (bx - head * sign, by + head / 2), (bx, by)]
    else:  # vertical final segment
        sign = 1.0 if by >= ay else -1.0
        tip = [(bx - head / 2, by - head * sign), (bx + head / 2, by - head * sign), (bx, by)]
    sym.add_polygon(g, tip)

    if geom.start_label:
        sym.add_text(g, points[0][0] - 14, points[0][1] - 6, geom.start_label, size=7.0)
    if geom.end_label:
        sym.add_text(g, points[-1][0] + 14, points[-1][1] - 6, geom.end_label, size=7.0)

    # Line number along the run.
    lx, ly, _ = _point_at_fraction(points, 0.35)
    sym.add_text(g, lx, ly - 5, line.number, size=7.0)
    return points


def _draw_inline(
    parent: ET.Element, line: PidLine, points: list[_Point], valves_by_tag: dict[str, Valve]
) -> None:
    n = len(line.items)
    for i, item in enumerate(line.items):
        t = (i + 1) / (n + 2)
        x, y, angle = _point_at_fraction(points, t)
        if item.kind == InlineKind.VALVE and item.ref in valves_by_tag:
            _draw_valve(parent, valves_by_tag[item.ref], x, y, angle)
        else:
            _draw_inline_item(parent, item.kind, x, y, angle)


def _draw_loose_valves(parent: ET.Element, pid: PID, y: float) -> float:
    """Valves no line references get a labelled symbol in a strip at the bottom."""
    referenced = {it.ref for ln in pid.lines for it in ln.items if it.kind == InlineKind.VALVE}
    loose = sorted((v for v in pid.valves if v.tag not in referenced), key=lambda v: v.tag)
    for i, v in enumerate(loose):
        x = MARGIN + i * 60.0
        _draw_valve(parent, v, x, y)
    return y + (24.0 if loose else 0.0)


def _draw_equipment(parent: ET.Element, pid: PID, placements: dict[str, _Placement]) -> None:
    for eq in sorted(pid.equipment, key=lambda e: e.tag):
        p = placements[eq.tag]
        sym.equipment_symbol(
            parent, eq.kind, p.bbox_x + p.bbox_w / 2, p.bbox_y + p.bbox_h / 2, p.bbox_w, p.bbox_h, eq.tag
        )


def _draw_instruments(
    parent: ET.Element,
    pid: PID,
    placements: dict[str, _Placement],
    line_points: dict[str, list[_Point]],
) -> None:
    per_equip: dict[str, int] = {}
    per_line: dict[str, int] = {}
    for inst in sorted(pid.instruments, key=lambda i: i.tag):
        target = inst.connected_to
        attach: _Point
        if target in placements:
            p = placements[target]
            idx = per_equip.get(target, 0)
            per_equip[target] = idx + 1
            cx = p.bbox_x + p.bbox_w / 2
            cy = p.bbox_y - 22 - idx * 32
            attach = (cx, p.bbox_y)
        elif target in line_points:
            idx = per_line.get(target, 0)
            per_line[target] = idx + 1
            pts = line_points[target]
            mid = _point_at_fraction(pts, 0.65)
            cx, cy = mid[0], mid[1] + 26 + idx * 32
            attach = (mid[0], mid[1])
        else:
            continue
        g = sym.group(parent)
        g.set("data-tag", inst.tag)
        sym.instrument_bubble(g, cx, cy, inst.function, inst.loop, inst.tag)
        sym.add_line(g, cx, cy + 13, attach[0], attach[1])


# --------------------------------------------------------------------------
# Plugin
# --------------------------------------------------------------------------


def render_pid_svg(pid: PID, placed: dict[str, XY] | None = None) -> str:
    """Render a PID to a complete SVG document string.

    ``placed`` maps equipment tag to a bbox top-left in view px (layout.pid
    overrides); unlisted tags keep the auto layout.
    """
    placements = _layout(pid, placed)

    # Canvas: equipment cells plus head-room for instrument bubbles and tags.
    width = max((p.bbox_x + p.bbox_w for p in placements.values()), default=0.0) + MARGIN + 100.0
    height = max((p.bbox_y + p.bbox_h for p in placements.values()), default=0.0) + MARGIN + 80.0
    root = sym.new_svg(width, height)

    # Lines first so equipment symbols draw on top of the connection runs.
    line_layer = sym.group(root)
    equip_layer = sym.group(root)
    inline_layer = sym.group(root)
    instr_layer = sym.group(root)

    line_points: dict[str, list[_Point]] = {}
    for line in sorted(pid.lines, key=lambda ln: ln.number):
        line_points[line.number] = _draw_line(line_layer, line, pid, placements)

    _draw_equipment(equip_layer, pid, placements)

    valves_by_tag = {v.tag: v for v in pid.valves}
    for line in sorted(pid.lines, key=lambda ln: ln.number):
        _draw_inline(inline_layer, line, line_points[line.number], valves_by_tag)
    _draw_loose_valves(inline_layer, pid, height - MARGIN)

    _draw_instruments(instr_layer, pid, placements, line_points)

    return ET.tostring(root, encoding="unicode")


@register("diagram", "pid")
class PidSvgRenderer:
    """Kind ``diagram``, name ``pid``: renders a :class:`PID` to SVG."""

    def render(self, obj: Any) -> str:
        if not isinstance(obj, PID):
            raise TypeError(f"pid renderer expects a PID, got {type(obj).__name__}")
        return render_pid_svg(obj)
