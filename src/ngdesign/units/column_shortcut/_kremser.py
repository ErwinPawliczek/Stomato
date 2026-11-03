"""Shared two-feed Kremser stage transfer (spec U-E).

One owner for the generalized split behind the absorber and reboiled
stripper adapters: Seader, Henley & Roper 3rd ed. eqs. (5-48)/(5-50)
(fractions not transferred) and (5-54)/(5-55) (outlet flows with both feeds).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ngdesign.contracts.stream import StreamState
from ngdesign.provenance.recorder import Recorder
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


# ---------------------------------------------------------------- provenance (tracing on only)


def trace_average_condition(
    rec: Recorder, a: StreamState, b: StreamState, t_avg: float, p_avg: float
) -> None:
    """Record the averaged inlet T and P the K-values are evaluated at."""
    rec.equation("T_avg", t_avg, "K", "average_condition", {"T_1": (a, "T"), "T_2": (b, "T")})
    rec.equation("P_avg", p_avg, "Pa", "average_condition", {"P_1": (a, "P"), "P_2": (b, "P")})


def trace_kremser_split(
    rec: Recorder,
    inputs: Mapping[str, Any],
    k_map: Mapping[str, float],
    sides: Sequence[tuple[str, Mapping[str, float], Mapping[str, float], float]],
    extra: Mapping[str, float],
) -> None:
    """Record the two-feed Kremser split (:func:`two_feed_split`) as one operation.

    ``sides`` is ``(name, outlet flows, outlet composition, outlet total)`` per outlet;
    the per-component outlet flows are results named ``<name>_<cid>`` (the unit's
    ``info`` names), ``extra`` further per-component results (fractions not
    transferred). The outlet compositions and totals are normalized from them.
    """
    outputs: dict[str, float] = {}
    for name, flows, _, _ in sides:
        outputs.update({f"{name}_{cid}": n for cid, n in flows.items()})
    outputs.update(extra)
    refs = rec.results(
        "kremser_split",
        outputs,
        {**inputs, **{f"K[{cid}]": k for cid, k in k_map.items()}},
    )
    for name, flows, z, total in sides:
        amounts = {f"n[{cid}]": refs[f"{name}_{cid}"] for cid in flows}
        rec.equation(f"z_{name}", z, "1", "mole_fractions", amounts)
        rec.equation(f"F_{name}", total, "mol/s", "mole_fractions", amounts)


def trace_two_feed_duty(
    rec: Recorder, duty: float, inlets: Sequence[StreamState], outlets: Sequence[StreamState]
) -> None:
    """Record ``duty = Σ F_out h_out - Σ F_in h_in`` over the unit's boundary streams."""
    inputs: dict[str, Any] = {}
    for k, s in enumerate(inlets):
        inputs[f"F_in{k}"] = (s, "molar_flow")
        inputs[f"h_in{k}"] = (s, "enthalpy")
    for k, s in enumerate(outlets):
        inputs[f"F_out{k}"] = (s, "molar_flow")
        inputs[f"h_out{k}"] = (s, "enthalpy")
    rec.equation("duty_W", duty, "W", "multi_stream_energy_balance", inputs)
