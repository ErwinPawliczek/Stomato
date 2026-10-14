"""SVG symbol primitives for the P&ID and PFD renderers (specs S-18, S-22).

ISA 5.1 / ISO 10628 style, simplified geometric symbols built with
``xml.etree`` — no external dependencies, fully deterministic output.

Every function here is pure: it takes a parent element and geometry and
appends child elements. Coordinates are SVG pixels, y increasing downwards.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

#: class attribute marking equipment bounding-box rects (used by tests
#: to verify placement invariants, and by the layout for hit boxes).
BBOX_CLASS = "equipment-bbox"

TEXT_SIZE = 8.0
TAG_TEXT_SIZE = 9.0
STROKE = "#1a1a1a"


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def new_svg(width: float, height: float) -> ET.Element:
    """Root ``<svg>`` element with a white background."""
    root = ET.Element(
        "svg",
        {
            "xmlns": SVG_NS,
            "width": _fmt(width),
            "height": _fmt(height),
            "viewBox": f"0 0 {_fmt(width)} {_fmt(height)}",
            "font-family": "Helvetica, Arial, sans-serif",
        },
    )
    ET.SubElement(
        root,
        "rect",
        {"x": "0", "y": "0", "width": _fmt(width), "height": _fmt(height), "fill": "#ffffff"},
    )
    return root


def group(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, "g")


def stroke_attrs(extra: dict[str, str] | None = None) -> dict[str, str]:
    a = {"fill": "none", "stroke": STROKE, "stroke-width": "1.2"}
    if extra:
        a.update(extra)
    return a


def add_text(
    parent: ET.Element,
    x: float,
    y: float,
    text: str,
    size: float = TEXT_SIZE,
    anchor: str = "middle",
) -> ET.Element:
    el = ET.SubElement(
        parent,
        "text",
        {
            "x": _fmt(x),
            "y": _fmt(y),
            "font-size": _fmt(size),
            "text-anchor": anchor,
            "fill": STROKE,
        },
    )
    el.text = text
    return el


def add_polyline(parent: ET.Element, points: list[tuple[float, float]]) -> ET.Element:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    return ET.SubElement(parent, "polyline", stroke_attrs({"points": pts}))


def add_line(parent: ET.Element, x1: float, y1: float, x2: float, y2: float) -> ET.Element:
    return ET.SubElement(
        parent,
        "line",
        stroke_attrs({"x1": _fmt(x1), "y1": _fmt(y1), "x2": _fmt(x2), "y2": _fmt(y2)}),
    )


def add_polygon(parent: ET.Element, points: list[tuple[float, float]]) -> ET.Element:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    return ET.SubElement(parent, "polygon", stroke_attrs({"points": pts}))


def add_circle(parent: ET.Element, cx: float, cy: float, r: float) -> ET.Element:
    return ET.SubElement(
        parent,
        "circle",
        stroke_attrs({"cx": _fmt(cx), "cy": _fmt(cy), "r": _fmt(r)}),
    )


def add_bbox(parent: ET.Element, x: float, y: float, w: float, h: float, tag: str) -> ET.Element:
    """Invisible bounding-box rect a test can parse back for placement checks."""
    return ET.SubElement(
        parent,
        "rect",
        {
            "x": _fmt(x),
            "y": _fmt(y),
            "width": _fmt(w),
            "height": _fmt(h),
            "class": BBOX_CLASS,
            "data-tag": tag,
            "fill": "none",
            "stroke": "none",
        },
    )


# --------------------------------------------------------------------------
# Equipment symbols. Each draws inside a (cx, cy, w, h) box and labels the
# tag above; the invisible bbox rect spans the full box.
# --------------------------------------------------------------------------


def _equipment_frame(parent: ET.Element, cx: float, cy: float, w: float, h: float, tag: str) -> ET.Element:
    g = group(parent)
    add_bbox(g, cx - w / 2, cy - h / 2, w, h, tag)
    if tag:
        add_text(g, cx, cy - h / 2 - 4, tag, size=TAG_TEXT_SIZE)
    return g


def vessel_symbol(parent: ET.Element, cx: float, cy: float, w: float, h: float, tag: str = "") -> None:
    """Vertical vessel / separator / column: rounded rectangle."""
    g = _equipment_frame(parent, cx, cy, w, h, tag)
    ET.SubElement(
        g,
        "rect",
        stroke_attrs(
            {
                "x": _fmt(cx - w / 2),
                "y": _fmt(cy - h / 2),
                "width": _fmt(w),
                "height": _fmt(h),
                "rx": _fmt(min(w, h) / 5),
            }
        ),
    )


def pump_symbol(parent: ET.Element, cx: float, cy: float, w: float, h: float, tag: str = "") -> None:
    """Pump: circle with discharge triangle."""
    g = _equipment_frame(parent, cx, cy, w, h, tag)
    r = min(w, h) / 2
    add_circle(g, cx, cy, r)
    add_polygon(
        g,
        [(cx - r / 2, cy - r / 2.6), (cx - r / 2, cy + r / 2.6), (cx + r / 2, cy)],
    )


def compressor_symbol(parent: ET.Element, cx: float, cy: float, w: float, h: float, tag: str = "") -> None:
    """Compressor: trapezoid narrowing towards the discharge (right)."""
    g = _equipment_frame(parent, cx, cy, w, h, tag)
    inset = h / 5
    add_polygon(
        g,
        [
            (cx - w / 2, cy - h / 2),
            (cx + w / 2, cy - inset),
            (cx + w / 2, cy + inset),
            (cx - w / 2, cy + h / 2),
        ],
    )


def exchanger_symbol(parent: ET.Element, cx: float, cy: float, w: float, h: float, tag: str = "") -> None:
    """Heat exchanger: circle with a zigzag through the centre."""
    g = _equipment_frame(parent, cx, cy, w, h, tag)
    r = min(w, h) / 2
    add_circle(g, cx, cy, r)
    n = 4
    span = w * 0.6
    step = span / n
    pts = [(cx - span / 2, cy)]
    for i in range(n):
        pts.append((cx - span / 2 + step * (i + 0.5), cy - r / 2.5 if i % 2 == 0 else cy + r / 2.5))
    pts.append((cx + span / 2, cy))
    add_polyline(g, pts)


def equipment_symbol(
    parent: ET.Element, kind: str, cx: float, cy: float, w: float, h: float, tag: str = ""
) -> None:
    """Dispatch an equipment kind string to its symbol. Unknown kinds draw a vessel."""
    k = kind.lower()
    if "pump" in k:
        pump_symbol(parent, cx, cy, w, h, tag)
    elif "compressor" in k:
        compressor_symbol(parent, cx, cy, w, h, tag)
    elif "exchanger" in k or "cooler" in k or "heater" in k or "shell" in k:
        exchanger_symbol(parent, cx, cy, w, h, tag)
    else:
        vessel_symbol(parent, cx, cy, w, h, tag)


# --------------------------------------------------------------------------
# Inline symbols (valves, reducers, drains, vents), drawn horizontally
# centred on (cx, cy); rotate the group for vertical runs.
# --------------------------------------------------------------------------

VALVE_SIZE = 20.0


def _rotated(parent: ET.Element, cx: float, cy: float, angle_deg: float) -> ET.Element:
    g = group(parent)
    if angle_deg % 360 != 0:
        g.set("transform", f"rotate({_fmt(angle_deg)} {_fmt(cx)} {_fmt(cy)})")
    return g


def _bowtie(g: ET.Element, cx: float, cy: float, s: float) -> None:
    add_polygon(
        g,
        [(cx - s / 2, cy - s / 3), (cx - s / 2, cy + s / 3), (cx, cy)],
    )
    add_polygon(
        g,
        [(cx, cy), (cx + s / 2, cy - s / 3), (cx + s / 2, cy + s / 3)],
    )


def valve_symbol(
    parent: ET.Element, kind: str, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    """Valve symbol by ValveType value (or any close string); generic bowtie fallback."""
    g = _rotated(parent, cx, cy, angle_deg)
    k = kind.lower()
    if k == "ball":
        _bowtie(g, cx, cy, size)
        add_circle(g, cx, cy, size / 8)
    elif k == "globe":
        _bowtie(g, cx, cy, size)
        add_circle(g, cx, cy, size / 7)
        ET.SubElement(g, "circle", {"cx": _fmt(cx), "cy": _fmt(cy), "r": _fmt(size / 7), "fill": STROKE})
    elif k == "check_swing" or k == "check_piston" or k == "check_dual_plate" or k == "check":
        add_polygon(g, [(cx - size / 2, cy - size / 3), (cx - size / 2, cy + size / 3), (cx + size / 4, cy)])
        add_line(g, cx + size / 2, cy - size / 3, cx + size / 2, cy + size / 3)
    elif k == "control":
        _bowtie(g, cx, cy, size)
        add_line(g, cx, cy - size / 3, cx, cy - size / 2 - 6)
        add_line(g, cx - size / 3, cy - size / 2 - 6, cx + size / 3, cy - size / 2 - 6)
    elif k == "psv":
        _bowtie(g, cx, cy, size)
        add_line(g, cx, cy - size / 3, cx, cy - size / 2 - 8)
        # spring zigzag
        pts = [(cx - size / 4, cy - size / 2 - 8)]
        for i in (0, 1, 2):
            pts.append(
                (
                    cx - size / 4 + size / 12 * (i * 2 + 1),
                    cy - size / 2 - 8 - 4 if i % 2 == 0 else cy - size / 2 - 8 + 4,
                )
            )
        pts.append((cx + size / 4, cy - size / 2 - 8))
        add_polyline(g, pts)
    elif k == "rupture_disc" or k == "blowdown" or k == "esd" or k == "gate" or k == "plug":
        _bowtie(g, cx, cy, size)
    else:  # butterfly, needle, unknown
        _bowtie(g, cx, cy, size)
        add_line(g, cx, cy - size / 3, cx, cy + size / 3)


def reducer_symbol(
    parent: ET.Element,
    cx: float,
    cy: float,
    angle_deg: float = 0.0,
    size: float = VALVE_SIZE,
    eccentric: bool = False,
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    off = size / 8 if eccentric else 0.0
    add_polygon(
        g,
        [
            (cx - size / 2, cy - size / 3),
            (cx + size / 2, cy - size / 6 + off),
            (cx + size / 2, cy + size / 6 + off),
            (cx - size / 2, cy + size / 3),
        ],
    )


def strainer_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    ET.SubElement(
        g,
        "rect",
        stroke_attrs(
            {
                "x": _fmt(cx - size / 2),
                "y": _fmt(cy - size / 3),
                "width": _fmt(size),
                "height": _fmt(size / 1.5),
            }
        ),
    )
    add_line(g, cx - size / 3, cy + size / 3, cx + size / 3, cy - size / 3)


def orifice_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    add_line(g, cx, cy - size / 3, cx, cy + size / 3)
    add_line(g, cx + 3, cy - size / 3, cx + 3, cy + size / 3)


def spec_break_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    add_line(g, cx - 2, cy - size / 3, cx - 6, cy + size / 3)
    add_line(g, cx + 4, cy - size / 3, cx, cy + size / 3)


def spectacle_blind_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    add_circle(g, cx - size / 4, cy, size / 5)
    add_circle(g, cx + size / 4, cy, size / 5)
    add_line(g, cx - size / 4, cy, cx + size / 4, cy)


def instrument_tap_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    g = _rotated(parent, cx, cy, angle_deg)
    add_circle(g, cx, cy, size / 6)


def drain_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    """Drain: open triangle pointing down with a short drop line."""
    g = _rotated(parent, cx, cy, angle_deg)
    add_polygon(g, [(cx - size / 4, cy - size / 4), (cx + size / 4, cy - size / 4), (cx, cy + size / 6)])
    add_line(g, cx, cy + size / 6, cx, cy + size / 2)


def vent_symbol(
    parent: ET.Element, cx: float, cy: float, angle_deg: float = 0.0, size: float = VALVE_SIZE
) -> None:
    """Vent: short riser with an arrow head pointing up."""
    g = _rotated(parent, cx, cy, angle_deg)
    add_line(g, cx, cy + size / 4, cx, cy - size / 4)
    add_polygon(g, [(cx - size / 5, cy - size / 6), (cx + size / 5, cy - size / 6), (cx, cy - size / 2)])


# --------------------------------------------------------------------------
# Instrument bubble (ISA 5.1): circle, function letters on top, loop below.
# --------------------------------------------------------------------------


def instrument_bubble(
    parent: ET.Element, cx: float, cy: float, function: str, loop: int, tag: str = ""
) -> None:
    r = 13.0
    add_circle(parent, cx, cy, r)
    add_text(parent, cx, cy - 1, function, size=7.0)
    add_text(parent, cx, cy + 8, str(loop), size=7.0)
    if tag:
        add_text(parent, cx, cy + r + 9, tag, size=6.5)
