"""Plan-view (plot plan) SVG of a routed piping network (spec B-05, P0-03).

Moved here from ``ngdesign.api.routes_plot``: the render package owns SVG
projections and consumes only the :class:`PipingNetwork` contract, like the
other renderers in this package. ``POST /api/route`` and
``GET /api/views/plot.svg`` call :func:`render_plot_svg` on the pipeline's
routed output.

Model space is millimetres (the router's unit); SVG y grows downwards, so
the projection flips y to keep north up.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from ngdesign.contracts import PipingNetwork, RoutedLine
from ngdesign.render.symbols import STROKE, _fmt, group, new_svg, stroke_attrs

#: Plan-view stroke and label sizes in model millimetres (the viewBox unit);
#: the drawing spans tens of metres, so hairline pixels would vanish.
STROKE_MM = 300.0
LABEL_MM = 700.0
MARGIN_MM = 3000.0


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
    """Plan view of the routed network: envelope footprints + line centrelines."""
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
