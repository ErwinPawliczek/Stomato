"""Plot plan + routing API (spec B-05).

POST /api/route and GET /api/views/plot.svg both serve the S-21 orthogonal
router's output for the current project: the same engine chain as
GET /api/views/pid.svg (solve seam shared with POST /api/solve, sizers run on
a copy, P&ID builder, every registered pid_rule to a fixed point) routed
through the project's ``layout.plot`` placements. With an empty
``layout.plot`` the routing is exactly the S-35 CLI demo's
``route(pid, layout={})`` — same router, same lines, same geometry — so both
routes render the routing itself, not a separate model. Moving equipment via
PUT /api/project/layout/plot/{tag} re-routes on the next request: routed
lengths follow the equipment.

POST /api/route returns the routed network as JSON: per line the ordered
components (mm centreline geometry, elbows, flanges) plus the equipment
envelopes. GET /api/views/plot.svg draws the same network as a plan view:
envelope footprints and each line's centreline projected onto the x-y plane
(north up), every equipment and line wrapped in a ``data-tag`` group like the
pfd/pid views.

A project whose unit kind has no registered plugin cannot be solved, so it
cannot be routed either: both routes answer 501 naming the kind, exactly like
POST /api/solve. Layout placements for tags that are no longer in the P&ID
are ignored (same policy as the pfd/pid views).
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from fastapi import APIRouter
from fastapi.responses import Response

from ngdesign import registry
from ngdesign.contracts import PipingNetwork, RoutedLine
from ngdesign.render.symbols import STROKE, _fmt, group, new_svg, stroke_attrs

router = APIRouter()

_SVG_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"image/svg+xml": {}}}}

#: Plan-view stroke and label sizes in model millimetres (the viewBox unit);
#: the drawing spans tens of metres, so hairline pixels would vanish.
STROKE_MM = 300.0
LABEL_MM = 700.0
MARGIN_MM = 3000.0


def _routed_network() -> PipingNetwork:
    """Route the current project: solve -> sizers -> builder -> rules -> S-21."""
    # Late imports: app.py owns the current project and registers this router,
    # so a module-level import would be circular (same pattern as routes_solve).
    from ngdesign.api.app import _project
    from ngdesign.api.routes_solve import solve
    from ngdesign.cli import _apply_rules, _rule_set, _run_sizers

    project = _project()
    # Sizers mutate the flowsheet with datasheets: run them on a copy so the
    # cached solve result (spec B-02) stays byte-identical to a bare solve.
    solved = _run_sizers(solve().model_copy(deep=True))
    pid = registry.create("pid_builder", "default").build(solved)
    pid = _apply_rules(pid, _rule_set(solved))
    # Placements for tags that left the P&ID are ignored, like layout.pfd/pid.
    tags = {eq.tag for eq in pid.equipment}
    layout = {tag: pos for tag, pos in project.layout.plot.items() if tag in tags}
    net: PipingNetwork = registry.create("router", "orthogonal").route(pid, layout)
    return net


def _plan_vertices(line: RoutedLine) -> list[tuple[float, float]]:
    """Centreline vertices projected to the x-y plane, duplicate joints removed."""
    pts = [(c.start.x, c.start.y) for c in line.components]
    last = line.components[-1].end
    pts.append((last.x, last.y))
    return [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]


def _extent(net: PipingNetwork) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over equipment footprints and line runs."""
    xs: list[float] = []
    ys: list[float] = []
    for env in net.equipment:
        xs.extend((env.min.x, env.max.x))
        ys.extend((env.min.y, env.max.y))
    for line in net.lines:
        for x, y in _plan_vertices(line):
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def render_plot_svg(net: PipingNetwork) -> str:
    """Plan view of the routed network: envelope footprints + line centrelines.

    Model space is millimetres (the router's unit); SVG y grows downwards, so
    the projection flips y to keep north up.
    """
    min_x, min_y, max_x, max_y = _extent(net)

    def x(v: float) -> float:
        return v - min_x + MARGIN_MM

    def y(v: float) -> float:
        return max_y + MARGIN_MM - v

    w = (max_x - min_x) + 2 * MARGIN_MM
    h = (max_y - min_y) + 2 * MARGIN_MM
    root = new_svg(w, h)

    for env in net.equipment:
        g = group(root)
        g.set("data-tag", env.tag)
        ET.SubElement(
            g,
            "rect",
            stroke_attrs(
                {
                    "x": _fmt(x(env.min.x)),
                    "y": _fmt(y(env.max.y)),
                    "width": _fmt(env.max.x - env.min.x),
                    "height": _fmt(env.max.y - env.min.y),
                    "stroke-width": _fmt(STROKE_MM),
                }
            ),
        )
        ET.SubElement(
            g,
            "text",
            {
                "x": _fmt(x((env.min.x + env.max.x) / 2)),
                "y": _fmt(y((env.min.y + env.max.y) / 2)),
                "font-size": _fmt(LABEL_MM),
                "text-anchor": "middle",
                "fill": STROKE,
            },
        ).text = env.tag

    for line in net.lines:
        g = group(root)
        g.set("data-tag", line.line_number)
        pts = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in ((x(a), y(b)) for a, b in _plan_vertices(line)))
        ET.SubElement(g, "polyline", stroke_attrs({"points": pts, "stroke-width": _fmt(STROKE_MM)}))

    return ET.tostring(root, encoding="unicode")


@router.post("/api/route")
def route() -> PipingNetwork:
    """Route the current project's P&ID through the layout.plot placements."""
    return _routed_network()


@router.get("/api/views/plot.svg", response_class=Response, responses=_SVG_RESPONSES)
def plot_svg() -> Response:
    """Top view of the current project's routed piping, plan north up."""
    return Response(content=render_plot_svg(_routed_network()), media_type="image/svg+xml")
