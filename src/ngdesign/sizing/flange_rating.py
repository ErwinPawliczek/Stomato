"""ASME B16.5 flange pressure-temperature ratings (spec S-11).

Ratings are read from `ngdesign.data.flange_ratings()` (ASME B16.5 Table 2
series, data/flanges_b165.csv) and linearly interpolated in temperature (degF).
At or below the lowest tabulated temperature the lowest-temperature rating
applies (the table starts at 100 F, so every temperature at or below 100 F uses
the 100 F value); above the highest tabulated temperature the request is out of
range and raises ValueError.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

from ngdesign.data import flange_ratings
from ngdesign.registry import register


def _rating_rows(material_group: str, flange_class: int) -> list[tuple[float, float]]:
    """Sorted (temp_F, max_pressure_psig) rows for one material group and class."""
    rows = [
        (float(r["temp_F"]), float(r["max_pressure_psig"]))
        for r in flange_ratings()
        if r["material_group"] == material_group and r["class"] == flange_class
    ]
    if not rows:
        raise ValueError(f"no B16.5 rating rows for material group {material_group!r} class {flange_class}")
    return sorted(rows)


def flange_rating_b165(material_group: str, flange_class: int, temp_F: float) -> float:
    """B16.5 maximum rated pressure (psig) for a flange at temperature.

    Linear interpolation in temp_F between tabulated rows; temperatures at or
    below the lowest tabulated temperature return that row's rating; above the
    highest tabulated temperature raises ValueError (extrapolation is not
    permitted for code ratings).
    """
    rows = _rating_rows(material_group, flange_class)
    temps = [t for t, _ in rows]
    pressures = [p for _, p in rows]

    if temp_F > temps[-1]:
        raise ValueError(
            f"temp_F {temp_F} above B16.5 table range for material group {material_group!r} "
            f"class {flange_class} (max {temps[-1]} F)"
        )
    if temp_F <= temps[0]:
        return pressures[0]

    i = bisect_left(temps, temp_F)
    if temps[i] == temp_F:
        return pressures[i]
    t0, t1 = temps[i - 1], temps[i]
    p0, p1 = pressures[i - 1], pressures[i]
    return p0 + (p1 - p0) * (temp_F - t0) / (t1 - t0)


def min_flange_class(material_group: str, design_pressure_psig: float, temp_F: float) -> int:
    """Lowest B16.5 class whose rating at temp_F is >= design pressure (psig).

    Raises ValueError for non-positive pressure, an unknown material group, a
    temperature above the table range, or when no class on file suffices.
    """
    if design_pressure_psig <= 0:
        raise ValueError(f"design_pressure_psig must be positive, got {design_pressure_psig}")
    classes = sorted({int(r["class"]) for r in flange_ratings() if r["material_group"] == material_group})
    if not classes:
        raise ValueError(f"unknown material group {material_group!r}")
    for flange_class in classes:
        if flange_rating_b165(material_group, flange_class, temp_F) >= design_pressure_psig:
            return flange_class
    raise ValueError(
        f"no B16.5 class for material group {material_group!r} rated "
        f"{design_pressure_psig} psig at {temp_F} F"
    )


@register("correlation", "flange_rating_b165")
class FlangeRatingB165:
    """Correlation plugin; contract is data/golden/flange_rating_b165.yaml."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return {"max_pressure_psig": flange_rating_b165(**inputs)}
