"""Shared two-feed Kremser stage transfer (spec U-E).

One owner for the generalized split behind the absorber and reboiled
stripper adapters: Seader, Henley & Roper 3rd ed. eqs. (5-48)/(5-50)
(fractions not transferred) and (5-54)/(5-55) (outlet flows with both feeds).
"""

from __future__ import annotations

from typing import Mapping

from ngdesign.units._physics.shortcut import kremser_fraction


def two_feed_split(
    gas_feed: Mapping[str, float],
    liquid_feed: Mapping[str, float],
    k_values: Mapping[str, float],
    liquid_flow: float,
    vapour_flow: float,
    stages: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Split component flows across N ideal stages, the generalized Kremser form.

    Args:
        gas_feed: component molar flows entering with the vapour, mol/s.
        liquid_feed: component molar flows entering with the liquid, mol/s.
        k_values: equilibrium K_i = y_i/x_i per component.
        liquid_flow: total liquid-phase feed flow L, mol/s.
        vapour_flow: total vapour-phase feed flow V, mol/s.
        stages: ideal stages N.

    Returns:
        (vapour-side outlet flows, liquid-side outlet flows), mol/s, over the
        union of the feed components. For a component in the gas feed with
        ``A_i = L/(K_i*V)`` the fraction not absorbed is ``1 - phi(A_i)``
        (eq. 5-48); for a component in the liquid feed with ``S_i = K_i*V/L``
        the fraction stripped is ``phi(S_i)`` (eq. 5-50); the vapour-side
        outlet combines both, eq. (5-54), and the liquid side closes the
        balance, eq. (5-55). ``phi`` is :func:`kremser_fraction`.

    Raises:
        ValueError: when a feed component has no K-value.
    """
    out_vapour: dict[str, float] = {}
    out_liquid: dict[str, float] = {}
    if liquid_flow <= 0.0 or vapour_flow <= 0.0:
        raise ValueError("both phase flows must be positive for the Kremser split")
    for cid in set(gas_feed) | set(liquid_feed):
        k = k_values.get(cid)
        if k is None or k <= 0.0:
            raise ValueError(f"component {cid!r} has no positive K-value for the Kremser split")
        g = gas_feed.get(cid, 0.0)
        liquid = liquid_feed.get(cid, 0.0)
        phi_abs = kremser_fraction(liquid_flow / (k * vapour_flow), stages)
        phi_strip = kremser_fraction(k * vapour_flow / liquid_flow, stages)
        vapour_out = g * (1.0 - phi_abs) + liquid * phi_strip
        out_vapour[cid] = vapour_out
        out_liquid[cid] = g + liquid - vapour_out
    return out_vapour, out_liquid
