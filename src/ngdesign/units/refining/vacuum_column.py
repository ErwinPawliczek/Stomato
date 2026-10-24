"""``vacuum_column`` adapter (spec U-H1).

Vacuum distillation of atmospheric residue at rigour R0: the same sharp
cut-point fractionation as the crude column, applied to the reduced-crude feed
at the flash-zone vacuum — pseudos split by ``Tb`` against ``cut_points_K``
into ``overhead``, ``vgo_out`` and ``bottoms``, with light ends and water
always reporting to the overhead. Each product is flashed at its draw
conditions (``draws`` param, default the feed T/P); ``info`` carries
per-product reference volumes and volume percentages of the feed.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units.refining._cuts import (
    LIGHT_ENDS_OVERHEAD,
    RefiningSpecError,
    draw_conditions,
    flash_product,
    optional_float,
    split_products,
    validate_draws,
)
from ngdesign.units.refining.slate import reference_volume

#: Product ports in cut order, lightest first (the catalogue row's outlet list).
_PRODUCTS = ("overhead", "vgo_out", "bottoms")


@register("unit", "vacuum_column")
class VacuumColumn:
    """Cut-point fractionation of atmospheric residue under vacuum."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = _PRODUCTS

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The light crude's heavy pseudos as vacuum feed at 40 mmHg (Gary et al. p. 77)."""
        from ngdesign.data import component_record
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        # Feed = pseudos boiling above the AGO end point (the atmospheric bottoms).
        heavy = {
            cid: x
            for cid, x in mole.items()
            if cid not in LIGHT_ENDS_OVERHEAD and component_record(cid)["Tb"] > 668.7
        }
        total = sum(heavy.values())
        composition = {cid: x / total for cid, x in heavy.items()}
        feeds = {
            "feed_in": {
                "T": 653.15,  # 380 degC, inside the printed 380-420 degC band
                "P": 5333.0,  # 40 mmHg absolute
                "molar_flow": 1000.0,
                "composition": composition,
            }
        }
        return feeds, {
            "cut_points_K": [755.0],
            "draws": {
                "vgo_out": {"T": 533.15, "P": 5333.0},
                "bottoms": {"T": 653.15, "P": 5333.0},
            },
        }

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Assign residue pseudos to vacuum products by NBP and flash each draw."""
        feed = inlets.get("feed_in")
        if feed is None:
            raise RefiningSpecError("feed_in: the reduced-crude inlet stream is required")
        raw_cuts = params.get("cut_points_K")
        if not isinstance(raw_cuts, list) or len(raw_cuts) != len(_PRODUCTS) - 1:
            raise RefiningSpecError(f"cut_points_K: needs exactly {len(_PRODUCTS) - 1} ascending values")
        cut_points = [_cut_point(raw_cuts[i], i) for i in range(len(raw_cuts))]
        if any(a >= b for a, b in zip(cut_points, cut_points[1:], strict=False)):
            raise RefiningSpecError("cut_points_K: values must be strictly ascending")
        overlap_k = optional_float(params, "overlap_K", 0.0)
        draws = params.get("draws")
        if draws is not None and not isinstance(draws, dict):
            raise RefiningSpecError("draws: must be a mapping of port to {T, P}")
        draws_typed = draws if isinstance(draws, dict) else None
        validate_draws(draws_typed, _PRODUCTS)

        products = split_products(feed, len(_PRODUCTS), cut_points, overlap_k)
        outlets: dict[str, StreamState] = {}
        for i, port in enumerate(_PRODUCTS):
            t_draw, p_draw = draw_conditions(port, draws_typed, feed.T, feed.P)
            outlets[port] = flash_product(thermo, products[i], t_draw, p_draw, feed)
        h_in = feed.enthalpy * feed.molar_flow
        h_out = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        info: dict[str, float] = {}
        feed_vol = reference_volume(feed)
        for port, state in outlets.items():
            info[f"{port}_vol_m3_s"] = reference_volume(state)
            info[f"{port}_vol_pct"] = 100.0 * info[f"{port}_vol_m3_s"] / feed_vol if feed_vol else 0.0
        return UnitResult(outlets=outlets, duty_W=h_out - h_in, power_W=0.0, info=info)


def _cut_point(raw: object, index: int) -> float:
    """One cut point out of a raw params list (bools rejected)."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RefiningSpecError(f"cut_points_K[{index}]: must be a number")
    return float(raw)
