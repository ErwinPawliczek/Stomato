"""S-21: orthogonal pipe router — P&ID lines to 3D routed lines via a rack.

Plugin: kind "router", name "orthogonal".

Layout: `layout` maps equipment tag -> origin Vec3 (mm), or a provided
EquipmentEnvelope (the equipment then sits at the envelope centre). Tags
absent from the layout are placed along x at 12 000 mm spacing at grade.
The optional "rack_elevation_mm" key overrides the rack elevation
(PipingNetwork.rack_elevation_mm, default 6000). Boundary line ends sit
3 000 mm beyond the first/last equipment x, at grade.

Each line routes: start nozzle -> leg along the nozzle facing (min 500 mm) ->
vertical to the rack elevation -> run along x -> run along y if needed ->
vertical to the end nozzle leg -> end nozzle. Zero-length legs collapse and
same-axis legs merge (a 180 deg reversal is not an elbow); every remaining
direction change becomes an ELBOW_90_LR. Nozzle legs extend in 1 000 mm steps
until every pipe segment clears the equipment envelopes; a line's own
connected equipment is exempt (its nozzle approach necessarily enters the
envelope). Weld-neck flanges sit
at equipment nozzle ends (placeholder length until H-01 dimensions land).
Pipe schedule comes from ngdesign.sizing.wall_thickness.select_schedule when
that module exists (imported lazily), else "40".

Out of scope (spec): optimal routing, clash avoidance between lines, slopes.
"""

from __future__ import annotations

import importlib
import math
from typing import Any, NamedTuple

from ngdesign.contracts import (
    PID,
    Component,
    ComponentKind,
    Direction,
    EndType,
    EquipmentEnvelope,
    LineEnd,
    PidLine,
    PipingNetwork,
    RoutedLine,
    Vec3,
)
from ngdesign.piping.fittings import WN_FLANGE_LENGTH_MM, elbow_90_lr_cte_mm
from ngdesign.registry import register

DEFAULT_RACK_ELEVATION_MM = 6000.0
DEFAULT_EQUIPMENT_SPACING_MM = 12_000.0
BOUNDARY_SETBACK_MM = 3_000.0
NOZZLE_LEG_MM = 500.0
DEFAULT_ENVELOPE_HALF_MM = 1_000.0  # 2 m cube around each origin
LEG_EXTENSION_MM = 1_000.0  # clearance retry step
LEG_EXTENSION_TRIES = 20
MIN_RUN_MM = 0.5  # same as the contract continuity tolerance
#: Same 100 mm workmanship margin the nozzle-leg length formula uses.
WORKMANSHIP_MARGIN_MM = 100.0
ATMOSPHERE_PA = 101_325.0
SCHEDULE_FALLBACK = "40"

_AXES: dict[Direction, tuple[float, float, float]] = {
    Direction.E: (1.0, 0.0, 0.0),
    Direction.W: (-1.0, 0.0, 0.0),
    Direction.N: (0.0, 1.0, 0.0),
    Direction.S: (0.0, -1.0, 0.0),
    Direction.UP: (0.0, 0.0, 1.0),
    Direction.DOWN: (0.0, 0.0, -1.0),
}


class _End(NamedTuple):
    """Resolved line end: world point, facing (None at a boundary), flange class."""

    point: Vec3
    facing: Direction | None
    flange_class: int | None = None


def _pt(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=x, y=y, z=z)


def _step(p: Vec3, axis: tuple[float, float, float], dist: float) -> Vec3:
    return _pt(p.x + axis[0] * dist, p.y + axis[1] * dist, p.z + axis[2] * dist)


def _between(a: Vec3, b: Vec3) -> tuple[float, float, float]:
    return (b.x - a.x, b.y - a.y, b.z - a.z)


def _leg_axis(a: Vec3, b: Vec3) -> tuple[float, float, float] | None:
    """Unit axis of a leg, or None for a zero-length leg."""
    dx, dy, dz = _between(a, b)
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n == 0.0:
        return None
    return (dx / n, dy / n, dz / n)


def _same_axis(u: tuple[float, float, float], v: tuple[float, float, float]) -> bool:
    """True for collinear or anti-parallel unit axes (dot = +-1)."""
    return abs(u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) > 1.0 - 1e-9


def segment_hits_envelope(a: Vec3, b: Vec3, env: EquipmentEnvelope) -> bool:
    """True if segment a-b intersects the axis-aligned envelope box (mm)."""
    lo = (env.min.x, env.min.y, env.min.z)
    hi = (env.max.x, env.max.y, env.max.z)
    origin = (a.x, a.y, a.z)
    delta = _between(a, b)
    t0, t1 = 0.0, 1.0
    for o, d, low, high in zip(origin, delta, lo, hi, strict=False):
        if abs(d) < 1e-12:
            if o < low or o > high:
                return False
            continue
        entering = (low - o) / d
        leaving = (high - o) / d
        if entering > leaving:
            entering, leaving = leaving, entering
        t0 = max(t0, entering)
        t1 = min(t1, leaving)
        if t0 > t1:
            return False
    return True


def _select_schedule(nps_in: float, design_gauge_Pa: float, pipe_class: str) -> str:
    """Schedule from the B31.3 module when it exists (spec S-02), else "40"."""
    try:
        wall_thickness = importlib.import_module("ngdesign.sizing.wall_thickness")
    except ImportError:
        return SCHEDULE_FALLBACK
    selector = getattr(wall_thickness, "select_schedule", None)
    if selector is None:
        return SCHEDULE_FALLBACK
    result = selector(nps_in, design_gauge_Pa, pipe_class)
    return str(result["selected_schedule"])


def _default_envelope(tag: str, origin: Vec3) -> EquipmentEnvelope:
    h = DEFAULT_ENVELOPE_HALF_MM
    return EquipmentEnvelope(
        tag=tag,
        min=_pt(origin.x - h, origin.y - h, origin.z - h),
        max=_pt(origin.x + h, origin.y + h, origin.z + h),
    )


def _origin_and_envelope(tag: str, value: Any) -> tuple[Vec3, EquipmentEnvelope]:
    if isinstance(value, Vec3):
        return value, _default_envelope(tag, value)
    if isinstance(value, EquipmentEnvelope):
        c = _pt(
            (value.min.x + value.max.x) / 2, (value.min.y + value.max.y) / 2, (value.min.z + value.max.z) / 2
        )
        return c, value
    raise ValueError(
        f"layout[{tag!r}] must be a Vec3 origin or EquipmentEnvelope, got {type(value).__name__}"
    )


def _layout(pid: PID, layout: dict[str, Any]) -> tuple[dict[str, Vec3], list[EquipmentEnvelope]]:
    """Origins and collision envelopes for every P&ID equipment tag."""
    reserved = {"rack_elevation_mm"}
    unknown = sorted(set(layout) - reserved - {eq.tag for eq in pid.equipment})
    if unknown:
        raise ValueError(f"layout keys not in P&ID equipment: {', '.join(unknown)}")
    origins: dict[str, Vec3] = {}
    envelopes: list[EquipmentEnvelope] = []
    placed = 0
    for eq in pid.equipment:
        if eq.tag in layout:
            origin, env = _origin_and_envelope(eq.tag, layout[eq.tag])
        else:
            placed += 1
            origin = _pt(DEFAULT_EQUIPMENT_SPACING_MM * placed, 0.0, 0.0)
            env = _default_envelope(eq.tag, origin)
        origins[eq.tag] = origin
        envelopes.append(env)
    if not origins:
        raise ValueError("P&ID has no equipment; nothing to route between")
    return origins, envelopes


def _boundaries(pid: PID, origins: dict[str, Vec3]) -> tuple[Vec3, Vec3]:
    """Boundary ends beyond the first/last equipment, at grade.

    The setback is BOUNDARY_SETBACK_MM unless a boundary line's nozzle
    geometry demands more: the rack run between the boundary column and the
    nozzle-leg corner must host the line's two elbows, so the boundary also
    clears the nozzle's reach toward it plus one leg-extension step of
    slack. (The fixed 3 000 mm setback left the locked e2e slice's feed
    line a 470 mm rack run that cannot host two 8 in elbows - surfaced by
    the S-35 end-to-end oracle.)
    """
    x0 = min(o.x for o in origins.values())
    x1 = max(o.x for o in origins.values())
    need_w, need_e = BOUNDARY_SETBACK_MM, BOUNDARY_SETBACK_MM
    for pl in pid.lines:
        if pl.start.boundary and not pl.end.boundary:
            need_w = max(need_w, _boundary_setback(pl, pl.end, pid, origins, x0, west=True))
        if pl.end.boundary and not pl.start.boundary:
            need_e = max(need_e, _boundary_setback(pl, pl.start, pid, origins, x1, west=False))
    return _pt(x0 - need_w, 0.0, 0.0), _pt(x1 + need_e, 0.0, 0.0)


def _boundary_setback(
    pl: PidLine,
    end: LineEnd,
    pid: PID,
    origins: dict[str, Vec3],
    edge_x: float,
    *,
    west: bool,
) -> float:
    """Setback so the rack run past this nozzle hosts the line's elbows."""
    cte = elbow_90_lr_cte_mm(pl.nps_in)
    leg = max(NOZZLE_LEG_MM, WN_FLANGE_LENGTH_MM + cte + 100.0)
    corner = _corner_x(pl, end, pid, origins, leg)
    if corner is None:
        return BOUNDARY_SETBACK_MM
    slack = 2.0 * cte + MIN_RUN_MM + WORKMANSHIP_MARGIN_MM
    gap = edge_x - corner if west else corner - edge_x
    return max(BOUNDARY_SETBACK_MM, gap + slack)


def _corner_x(
    pl: PidLine,
    end: LineEnd,
    pid: PID,
    origins: dict[str, Vec3],
    leg_len: float,
) -> float | None:
    """World x where the rack run meets this nozzle leg, or None.

    Mirrors _chain: a W-facing nozzle's corner sits leg_len west of the
    nozzle, an E-facing one leg_len east, a vertical one directly above it.
    Returns None for ends the router's own resolution will reject with the
    informative error, so this helper never raises first.
    """
    eq = next((e for e in pid.equipment if e.tag == end.equipment), None) if end.equipment else None
    if eq is None or end.nozzle is None:
        return None
    noz = next((n for n in eq.nozzles if n.id == end.nozzle), None)
    if noz is None:
        return None
    px = origins[eq.tag].x + noz.position_mm.x
    if noz.facing is Direction.W:
        return px - leg_len
    if noz.facing is Direction.E:
        return px + leg_len
    return px


def _resolve_end(end: LineEnd, pid: PID, origins: dict[str, Vec3], boundary: Vec3, which: str) -> _End:
    """Nozzle world point and facing, or the boundary point with no facing."""
    if end.equipment and end.nozzle:
        eq = next((e for e in pid.equipment if e.tag == end.equipment), None)
        if eq is None:
            raise ValueError(f"line {which} references unknown equipment {end.equipment}")
        noz = next((n for n in eq.nozzles if n.id == end.nozzle), None)
        if noz is None:
            raise ValueError(f"line {which} references unknown nozzle {end.equipment}/{end.nozzle}")
        origin = origins[eq.tag]
        return _End(
            _pt(origin.x + noz.position_mm.x, origin.y + noz.position_mm.y, origin.z + noz.position_mm.z),
            noz.facing,
            noz.flange_class,
        )
    if end.boundary:
        return _End(boundary, None)
    raise ValueError(
        f"line {which} is a tie-in to another line; "
        "the orthogonal router routes nozzle and boundary ends only"
    )


def _collapse(points: list[Vec3]) -> list[Vec3]:
    """Drop zero-length legs, merge same-axis legs; repeat to a fixpoint.

    Anti-parallel neighbours (a 180 deg reversal) cannot be represented by a
    90 deg elbow, so they merge into one straight leg like collinear ones.
    """
    pts = [p for i, p in enumerate(points) if i == 0 or _between(points[i - 1], p) != (0.0, 0.0, 0.0)]
    changed = True
    while changed and len(pts) > 2:
        changed = False
        for i in range(len(pts) - 2):
            u = _leg_axis(pts[i], pts[i + 1])
            v = _leg_axis(pts[i + 1], pts[i + 2])
            if u is not None and v is not None and _same_axis(u, v):
                pts.pop(i + 1)
                changed = True
                break
    return pts


def _y_reach(leg_len: float, axis: tuple[float, float, float], cte: float) -> float:
    """Corner offset along a nozzle axis.

    A north/south offset shifts the rack run in y, which inserts a y-leg
    between the x-run and the drop - an interior leg hosting elbows at both
    ends, so it must clear two centre-to-ends, not the nozzle-leg minimum
    (the S-35 slice's E-101 -> T-101 8 in line proved 504.8 mm too short for
    609.6 mm of elbows). East/west or vertical offsets keep the nozzle-leg
    length: their legs host a single elbow.
    """
    if axis[1]:
        return max(leg_len, 2.0 * cte + WORKMANSHIP_MARGIN_MM)
    return leg_len


def _chain(start: _End, end: _End, rack: float, leg_len: float, flange_len: float, cte: float) -> list[Vec3]:
    """Raw waypoint chain of the canonical profile, before collapsing."""
    pts: list[Vec3] = []
    if start.facing is None:
        pts.append(start.point)
    else:
        u = _AXES[start.facing]
        pts.append(_step(start.point, u, flange_len))  # start flange face
        pts.append(_step(start.point, u, _y_reach(leg_len, u, cte)))  # corner above the start leg
    last = pts[-1]
    pts.append(_pt(last.x, last.y, rack))  # rise/drop to the rack
    if end.facing is None:
        e_corner = end.point
        e_face = end.point
    else:
        u = _AXES[end.facing]
        e_corner = _step(end.point, u, _y_reach(leg_len, u, cte))
        e_face = _step(end.point, u, flange_len)
    last = pts[-1]
    pts.append(_pt(e_corner.x, last.y, rack))  # run along x
    pts.append(_pt(e_corner.x, e_corner.y, rack))  # run along y if needed
    pts.append(e_corner)  # drop to the end nozzle leg
    if end.facing is not None:
        pts.append(e_face)  # end nozzle leg
    return _collapse(pts)


def _pipe_description(nps_in: float, schedule: str) -> str:
    return f'{nps_in:g}" pipe SCH{schedule}'


def _elbow_description(nps_in: float, schedule: str) -> str:
    return f'{nps_in:g}" 90 LR elbow SCH{schedule}'


def _flange_description(nps_in: float, flange_class: int) -> str:
    return f'{nps_in:g}" WN flange cl{flange_class} RTJ'


class _Builder:
    """Assembles the component chain of one routed line from its waypoints."""

    def __init__(self, line: PidLine, schedule: str) -> None:
        self.line = line
        self.schedule = schedule
        self.cte = elbow_90_lr_cte_mm(line.nps_in)
        self.components: list[Component] = []
        self.counter = 0

    def _next_id(self) -> str:
        self.counter += 1
        return f"C{self.counter}"

    def _flange(self, start: Vec3, end: Vec3, end_types: tuple[EndType, EndType], flange_class: int) -> None:
        self.components.append(
            Component(
                id=self._next_id(),
                kind=ComponentKind.FLANGE_WN,
                nps_in=self.line.nps_in,
                pipe_class=self.line.pipe_class,
                schedule=self.schedule,
                start=start,
                end=end,
                end_types=end_types,
                description=_flange_description(self.line.nps_in, flange_class),
            )
        )

    def _pipe(self, start: Vec3, end: Vec3) -> None:
        self.components.append(
            Component(
                id=self._next_id(),
                kind=ComponentKind.PIPE,
                nps_in=self.line.nps_in,
                pipe_class=self.line.pipe_class,
                schedule=self.schedule,
                start=start,
                end=end,
                end_types=(EndType.BUTT_WELD, EndType.BUTT_WELD),
                description=_pipe_description(self.line.nps_in, self.schedule),
            )
        )

    def _elbow(
        self, corner: Vec3, incoming: tuple[float, float, float], outgoing: tuple[float, float, float]
    ) -> None:
        self.components.append(
            Component(
                id=self._next_id(),
                kind=ComponentKind.ELBOW_90_LR,
                nps_in=self.line.nps_in,
                pipe_class=self.line.pipe_class,
                schedule=self.schedule,
                start=_step(corner, incoming, -self.cte),
                end=_step(corner, outgoing, self.cte),
                center=corner,
                end_types=(EndType.BUTT_WELD, EndType.BUTT_WELD),
                description=_elbow_description(self.line.nps_in, self.schedule),
            )
        )

    def build(self, chain: list[Vec3], start: _End, end: _End) -> list[Component]:
        axes: list[tuple[float, float, float]] = []
        for i in range(len(chain) - 1):
            ax = _leg_axis(chain[i], chain[i + 1])
            if ax is None:
                raise ValueError(f"{self.line.number}: collapsed chain repeats a point")
            axes.append(ax)
        if start.facing is not None:
            if start.flange_class is None:
                raise ValueError(f"{self.line.number}: start nozzle has no flange class")
            self._flange(start.point, chain[0], (EndType.FLANGED, EndType.BUTT_WELD), start.flange_class)
        last = len(axes) - 1
        for i, axis in enumerate(axes):
            if i > 0:
                self._elbow(chain[i], axes[i - 1], axis)
            run = _between(chain[i], chain[i + 1])
            leg_mm = math.sqrt(sum(c * c for c in run))
            start_setback = 0.0 if i == 0 else self.cte
            end_setback = 0.0 if i == last else self.cte
            if leg_mm - start_setback - end_setback <= MIN_RUN_MM:
                raise ValueError(
                    f"{self.line.number}: leg {i} of {leg_mm:.1f} mm cannot host its elbows "
                    f"({start_setback + end_setback:.1f} mm of centre-to-end); move the equipment apart"
                )
            seg_start = chain[i] if i == 0 else _step(chain[i], axis, self.cte)
            seg_end = chain[i + 1] if i == last else _step(chain[i + 1], axis, -self.cte)
            self._pipe(seg_start, seg_end)
        if end.facing is not None:
            if end.flange_class is None:
                raise ValueError(f"{self.line.number}: end nozzle has no flange class")
            self._flange(chain[-1], end.point, (EndType.BUTT_WELD, EndType.FLANGED), end.flange_class)
        return self.components


def _envelope_clash(
    components: list[Component], envelopes: list[EquipmentEnvelope], exempt: set[str]
) -> str | None:
    """First pipe segment through a foreign equipment envelope, if any.

    A line's final approach to its own nozzle necessarily enters that
    equipment's envelope (the nozzle sits on the shell), so the connected
    equipment tags are exempt; every other envelope must stay clear.
    """
    for c in components:
        if c.kind != ComponentKind.PIPE:
            continue
        for env in envelopes:
            if env.tag not in exempt and segment_hits_envelope(c.start, c.end, env):
                return f"{c.id} ({c.description}) passes through {env.tag}"
    return None


@register("router", "orthogonal")
class OrthogonalRouter:
    """Routes P&ID lines as orthogonal 3D lines through a pipe rack (spec S-21)."""

    def route(self, pid: PID, layout: dict[str, Any]) -> PipingNetwork:
        rack = float(layout.get("rack_elevation_mm", DEFAULT_RACK_ELEVATION_MM))
        origins, envelopes = _layout(pid, layout)
        boundary_start, boundary_end = _boundaries(pid, origins)
        lines = [
            self._route_line(pl, pid, origins, envelopes, rack, boundary_start, boundary_end)
            for pl in pid.lines
        ]
        return PipingNetwork(lines=lines, equipment=envelopes, rack_elevation_mm=rack)

    def _route_line(
        self,
        pl: PidLine,
        pid: PID,
        origins: dict[str, Vec3],
        envelopes: list[EquipmentEnvelope],
        rack: float,
        boundary_start: Vec3,
        boundary_end: Vec3,
    ) -> RoutedLine:
        start = _resolve_end(pl.start, pid, origins, boundary_start, f"{pl.number} start")
        end = _resolve_end(pl.end, pid, origins, boundary_end, f"{pl.number} end")
        cte = elbow_90_lr_cte_mm(pl.nps_in)
        leg_len = max(NOZZLE_LEG_MM, WN_FLANGE_LENGTH_MM + cte + 100.0)
        schedule = _select_schedule(pl.nps_in, pl.design_pressure_Pa - ATMOSPHERE_PA, pl.pipe_class)
        for _ in range(LEG_EXTENSION_TRIES):
            chain = _chain(start, end, rack, leg_len, WN_FLANGE_LENGTH_MM, cte)
            components = _Builder(pl, schedule).build(chain, start, end)
            exempt = {t for t in (pl.start.equipment, pl.end.equipment) if t}
            clash = _envelope_clash(components, envelopes, exempt)
            if clash is None:
                return RoutedLine(line_number=pl.number, components=components)
            if start.facing is None and end.facing is None:
                break  # boundary-to-boundary: no leg to extend
            leg_len += LEG_EXTENSION_MM
        raise ValueError(
            f"{pl.number}: no nozzle leg length up to {leg_len:.0f} mm clears the equipment "
            f"envelopes ({clash}); adjust the layout"
        )
