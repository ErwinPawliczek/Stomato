"""``crude_column`` adapter (spec U-H1).

Atmospheric crude column at rigour R0: a sharp cut-point fractionation. Pseudos
in the feed are assigned to products by normal boiling point (``Tb`` from the
component records — the A-01 slate ids encode it) against an ascending list of
``cut_points_K`` — K boundaries for K+1 products — with an optional linear
``overlap_K`` band splitting a pseudo between two neighbouring cuts. Real light
ends (C1-C4) and water go to the overhead regardless of boiling point. An
optional ``stripping_steam`` inlet sends its water (H2O) to the overhead as
well (Watkins-style stripping steam at R0, one net duty). Each product is
flashed at its draw conditions (``draws`` param, default the feed T/P); the
reported ``duty_W`` is the one net column duty implied by the product states
(no internal condensing / stripping stages at this level — see the family
spec's R1/R2 ladder).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining._cuts import (
    RefiningSpecError,
    draw_conditions,
    flash_product,
    optional_float,
    split_products,
    validate_draws,
)
from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
from ngdesign.units.refining.slate import assay_slate, reference_volume, register_slate

#: Product ports in cut order, lightest first (the catalogue row's outlet list).
_PRODUCTS = ("overhead", "kero_out", "diesel_out", "ago_out", "bottoms")

#: Component id the stripping steam carries.
WATER_ID = "H2O"


class CrudeColumn:
    """Cut-point fractionation of an assay slate into five products."""

    inlet_ports: tuple[str, ...] = ("crude_in", "stripping_steam")
    outlet_ports: tuple[str, ...] = _PRODUCTS

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The light crude at the paper's flash-zone conditions; cuts from the specs."""
        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        feeds = {
            "crude_in": {
                "T": 631.75,  # 358.6 degC flash zone, Bagajewicz & Ji Table 5
                "P": 2.0e5,
                "molar_flow": 1000.0,
                "composition": dict(mole),
            },
            # Saturated stripping steam at the flash-zone pressure; its H2O
            # reports to the overhead (R0, one net duty).
            "stripping_steam": {
                "T": 393.37,  # sat. steam at 2.0e5 Pa
                "P": 2.0e5,
                "molar_flow": 10.0,
                "composition": {"H2O": 1.0},
            },
        }
        return feeds, {
            "cut_points_K": [462.5, 556.5, 614.5, 668.7],
            "overlap_K": 0.0,
        }

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Assign pseudos to products by NBP and flash each at its draw conditions."""
        feed = inlets.get("crude_in")
        if feed is None:
            raise RefiningSpecError("crude_in: the crude inlet stream is required")
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
        steam = inlets.get("stripping_steam")
        steam_flow = 0.0
        steam_enthalpy_term = 0.0
        if steam is not None and steam.molar_flow > 0.0:
            steam_water = steam.composition.get(WATER_ID, 0.0) * steam.molar_flow
            if steam_water > 0.0:
                products[0][WATER_ID] = products[0].get(WATER_ID, 0.0) + steam_water
            steam_flow = steam.molar_flow
            steam_enthalpy_term = steam.enthalpy * steam.molar_flow
        outlets: dict[str, StreamState] = {}
        for i, port in enumerate(_PRODUCTS):
            t_draw, p_draw = draw_conditions(port, draws_typed, feed.T, feed.P)
            outlets[port] = flash_product(thermo, products[i], t_draw, p_draw, feed)
        h_in = feed.enthalpy * feed.molar_flow + steam_enthalpy_term
        h_out = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        info: dict[str, float] = {}
        if steam_flow > 0.0:
            info["stripping_steam_mol_s"] = steam_flow
        outlet_vol = {port: reference_volume(state) for port, state in outlets.items()}
        total_vol = sum(outlet_vol.values())
        for port, vol in outlet_vol.items():
            info[f"{port}_vol_m3_s"] = vol
            info[f"{port}_vol_pct"] = 100.0 * vol / total_vol if total_vol else 0.0
        return UnitResult(outlets=outlets, duty_W=h_out - h_in, power_W=0.0, info=info)


def _cut_point(raw: object, index: int) -> float:
    """One cut point out of a raw params list (bools rejected)."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RefiningSpecError(f"cut_points_K[{index}]: must be a number")
    return float(raw)


def _flash_product(
    thermo: Thermo,
    flows: dict[str, float],
    t_draw: float,
    p_draw: float,
    feed: StreamState,
) -> StreamState:
    """Flash one product's component flows at (T, P); zero flow mirrors the feed."""
    total = sum(flows.values())
    if total <= 0.0:
        return feed.model_copy(update={"T": t_draw, "P": p_draw, "molar_flow": 0.0, "phases": []})
    composition = {cid: n / total for cid, n in flows.items() if n > 0.0}
    return thermo.flash_pt(composition, t_draw, p_draw, total)
