"""Shared cut-point arithmetic for the column adapters (spec U-H1).

Both column adapters assign pseudos to products by normal boiling point
(``Nbp``, from the A-01 slate ids) against an ascending list of cut points,
optionally with a linear overlap band that splits a pseudo between two
neighbouring products. Light ends and water are always routed to the
overhead. All refusal messages name the offending parameter.
"""

from __future__ import annotations


class RefiningSpecError(ValueError):
    """A refining unit adapter received a spec it cannot honour (parameter named)."""


#: Light ends and water forced to the overhead regardless of boiling point.
LIGHT_ENDS_OVERHEAD = frozenset({"C1", "C2", "C3", "iC4", "nC4", "H2O"})


def cut_fractions(nbp: float, cut_points: list[float], overlap_k: float) -> list[float]:
    """Fractions of one pseudo (``nbp`` in K) assigned to each product.

    With ``len(cut_points) == K`` there are ``K + 1`` products. ``overlap_k``
    is the half-width of a linear band around each cut point inside which the
    pseudo is split between the two neighbouring products (the fraction going
    to the lighter product falls linearly from 1 to 0 across the band). Bands
    must not overlap. The returned fractions sum to 1.
    """
    if overlap_k < 0.0:
        raise RefiningSpecError(f"overlap_K: must be >= 0, got {overlap_k}")
    if overlap_k > 0.0:
        for lo, hi in zip(cut_points, cut_points[1:]):
            if hi - lo <= 2.0 * overlap_k:
                raise RefiningSpecError(
                    f"overlap_K: bands around cut points {lo} K and {hi} K overlap"
                )
        # Disjoint bands: at most one boundary can hold this nbp.
        for i, cp in enumerate(cut_points):
            if abs(nbp - cp) < overlap_k:
                light = (cp + overlap_k - nbp) / (2.0 * overlap_k)
                fractions = [0.0] * (len(cut_points) + 1)
                fractions[i] = light
                fractions[i + 1] = 1.0 - light
                return fractions
    index = sum(1 for cp in cut_points if cp <= nbp)
    if index == 0:
        return [1.0] + [0.0] * len(cut_points)
    if index == len(cut_points):
        return [0.0] * len(cut_points) + [1.0]
    fractions = [0.0] * (len(cut_points) + 1)
    fractions[index] = 1.0
    return fractions


def require_float(params: dict[str, object], key: str) -> float:
    """A required numeric parameter (bools rejected); raises ``RefiningSpecError``."""
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefiningSpecError(f"{key}: a number is required")
    return float(value)


def optional_float(params: dict[str, object], key: str, default: float) -> float:
    """An optional numeric parameter (bools rejected); raises ``RefiningSpecError``."""
    value = params.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefiningSpecError(f"{key}: must be a number if given")
    return float(value)


def split_products(
    feed: object,
    product_count: int,
    cut_points: list[float],
    overlap_k: float,
) -> list[dict[str, float]]:
    """Per-product component mole flows from ``feed`` (light ends and water to cut 0).

    ``feed`` is a ``StreamState``-like object with ``composition`` and
    ``molar_flow``; every non-light-end component must resolve to a component
    record with a ``Tb`` (a pseudo-component slate).
    """
    from ngdesign.data import component_record

    products: list[dict[str, float]] = [{} for _ in range(product_count)]
    for cid, x in feed.composition.items():
        n = x * feed.molar_flow
        if cid in LIGHT_ENDS_OVERHEAD:
            products[0][cid] = products[0].get(cid, 0.0) + n
            continue
        record = component_record(cid)
        if "Tb" not in record:
            raise RefiningSpecError(
                f"cut_points_K: component {cid} has no normal boiling point; "
                "cut-point fractionation needs a pseudo-component slate"
            )
        fractions = cut_fractions(record["Tb"], cut_points, overlap_k)
        for i, f in enumerate(fractions):
            if f > 0.0:
                products[i][cid] = products[i].get(cid, 0.0) + f * n
    return products


def flash_product(
    thermo: object,
    flows: dict[str, float],
    t_draw: float,
    p_draw: float,
    reference: object,
) -> object:
    """Flash one product's component flows at (T, P); zero flow mirrors ``reference``."""
    total = sum(flows.values())
    if total <= 0.0:
        return reference.model_copy(
            update={"T": t_draw, "P": p_draw, "molar_flow": 0.0, "phases": []}
        )
    composition = {cid: n / total for cid, n in flows.items() if n > 0.0}
    return thermo.flash_pt(composition, t_draw, p_draw, total)


def draw_conditions(
    port: str, draws: dict[str, dict[str, float]] | None, feed_t: float, feed_p: float
) -> tuple[float, float]:
    """Outlet (T, P) for draw ``port``: the explicit ``draws`` entry or the feed state."""
    if draws is None:
        return feed_t, feed_p
    entry = draws.get(port)
    if entry is None:
        raise RefiningSpecError(f"draws: no entry for outlet port {port!r}")
    unknown = set(entry) - {"T", "P"}
    if unknown:
        raise RefiningSpecError(f"draws[{port!r}]: unknown keys {sorted(unknown)}")
    return entry.get("T", feed_t), entry.get("P", feed_p)


def validate_draws(
    draws: dict[str, dict[str, float]] | None, outlet_ports: tuple[str, ...]
) -> None:
    """Every ``draws`` key must be a declared outlet port."""
    if draws is None:
        return
    unknown = set(draws) - set(outlet_ports)
    if unknown:
        raise RefiningSpecError(f"draws: unknown port(s) {sorted(unknown)}")
