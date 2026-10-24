"""FUG shortcut distillation column, R0 (spec U-E).

Plugin kind "unit", name "shortcut_distillation". Ports feed -> distillate +
bottoms. Method (spec): Fenske-Underwood-Gilliland on the two key components
with the non-key distribution iterated to a fixed point at Nmin
(Hengstebeck-Geddes), the feed stage from Kirkbride, at R0 level:

1. Key recoveries in params fix the key product flows: distillate LK by
   ``recovery_LK_D``, bottoms HK by ``recovery_HK_B``.
2. Relative volatilities come from the package's saturation points: each
   product is flashed at its pressure, its bubble-point (or dew-point for a
   partial condenser) K-values are ``y_incipient/x`` (``x_incipient/y``), and
   the column alpha is the geometric mean of top and bottom; feed alphas use
   the feed state's own phase (bubble/dew incipient compositions when the
   feed arrives single-phase, ``thermo.k_values`` when two-phase).
3. Non-key splits iterate ``d_i/b_i = alpha_i**Nmin * d_HK/b_HK`` (Fenske at
   Nmin) until the distillate flows stop moving.
4. ``Nmin`` from Fenske, ``theta`` from Underwood's Class-2 root between the
   keys, ``Rmin`` from the distillate composition, ``N`` from Gilliland at
   the given reflux (``R`` or ``R_over_Rmin``), ``feed_stage`` from Kirkbride.
5. Distillate at its bubble point (total condenser) or dew point (partial);
   bottoms at its bubble point; condenser duty from condensing the overhead
   vapour, reboiler duty closing the balance; ``duty_W`` = reboiler -
   condenser with both in info.

Raises typed ValueErrors on missing keys, recoveries outside (0, 1), an
unknown condenser kind, ``R <= Rmin`` (no feasible separation), or an
unbracketed Underwood root.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.shortcut import (
    fenske_nmin,
    gilliland,
    kirkbride,
    underwood_rmin,
    underwood_theta,
)

#: Seader-Henley Example 9.2-9.7 debutanizer basis (pp. 350-360), used as the
#: adapter's example case: 876.3 lbmol/h of a hydrocarbon feed at 180 F / 80
#: psia, keys nC4 (recover 442 of 448 lbmol/h overhead) and iC5 (recover 23
#: of 36 lbmol/h in the bottoms), total condenser at 80 psia top and bottom,
#: R/Rmin = 1.688 (the book's R = 0.808 on Rmin = 0.479).
_EXAMPLE_FEED_LBMOL_H = {
    "iC4": 12.0,
    "nC4": 448.0,
    "iC5": 36.0,
    "nC5": 15.0,
    "nC6": 23.0,
    "nC7": 39.1,
    "nC8": 272.2,
    "nC9": 31.0,
}
_EXAMPLE_FEED_T = 355.3722  # 180 F, K
_EXAMPLE_P = 551580.6  # 80 psia, Pa
_EXAMPLE_RECOVERY_LK_D = 442.0 / 448.0
_EXAMPLE_RECOVERY_HK_B = 23.0 / 36.0
_EXAMPLE_R_OVER_RMIN = 1.688

#: lbmol/h -> mol/s (0.45359237 kmol per lbmol, 3600 s per h).
_LBMOL_H_TO_MOL_S = 0.45359237 / 3.6


def _bubble_k(
    thermo: Thermo, z: dict[str, float], pressure: float
) -> tuple[float, dict[str, float]]:
    """Bubble-point temperature and K-values ``y_incipient/x`` at pressure."""
    sat = thermo.bubble_point(z, P=pressure)
    k = {cid: sat.incipient_composition[cid] / x for cid, x in z.items() if x > 0.0}
    return sat.T, k


def _dew_k(
    thermo: Thermo, z: dict[str, float], pressure: float
) -> tuple[float, dict[str, float]]:
    """Dew-point temperature and K-values ``x/x_incipient`` at pressure."""
    sat = thermo.dew_point(z, P=pressure)
    k = {cid: x / sat.incipient_composition[cid] for cid, x in z.items() if x > 0.0}
    return sat.T, k


def _feed_k(thermo: Thermo, feed: StreamState) -> dict[str, float]:
    """K-values at the feed condition, whatever phase the feed arrives in."""
    if feed.vapor_fraction <= 1e-8:
        _, k = _bubble_k(thermo, feed.composition, feed.P)
        return k
    if feed.vapor_fraction >= 1.0 - 1e-8:
        _, k = _dew_k(thermo, feed.composition, feed.P)
        return k
    ks = thermo.k_values(feed.composition, feed.T, feed.P)
    if ks is None:
        raise ValueError(
            "shortcut_distillation: thermo gives no K-values for the two-phase feed at "
            f"({feed.T:.2f} K, {feed.P:.0f} Pa)"
        )
    return ks


class ShortcutDistillation:
    """FUG shortcut distillation (design-determined), R0: balances plus key
    recoveries and a reflux-ratio spec."""

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ValueError("shortcut_distillation needs a feed inlet stream")
        if feed.molar_flow <= 0.0:
            raise ValueError("shortcut_distillation feed flow must be positive")
        lk = params.get("light_key")
        hk = params.get("heavy_key")
        if not lk or not hk:
            raise ValueError("shortcut_distillation requires 'light_key' and 'heavy_key' params")
        if lk == hk:
            raise ValueError("shortcut_distillation light_key and heavy_key must differ")
        if lk not in feed.composition or hk not in feed.composition:
            raise ValueError(f"shortcut_distillation keys {lk!r}/{hk!r} must both appear in the feed")
        recovery_lk = float(params.get("recovery_LK_D", 1.0))
        recovery_hk = float(params.get("recovery_HK_B", 1.0))
        for name, value in (("recovery_LK_D", recovery_lk), ("recovery_HK_B", recovery_hk)):
            if not 0.0 < value < 1.0:
                raise ValueError(f"shortcut_distillation {name} must lie in (0, 1), got {value}")
        condenser = params.get("condenser", "total")
        if condenser not in ("total", "partial"):
            raise ValueError(
                f"shortcut_distillation condenser must be 'total' or 'partial', got {condenser!r}"
            )
        p_top = float(params["P_top"]) if params.get("P_top") is not None else feed.P
        p_bottom = float(params["P_bottom"]) if params.get("P_bottom") is not None else p_top
        if params.get("R") is not None:
            reflux = float(params["R"])
        elif params.get("R_over_Rmin") is not None:
            reflux = float(params["R_over_Rmin"])  # applied after Rmin below
        else:
            raise ValueError("shortcut_distillation requires 'R' or 'R_over_Rmin'")
        if reflux <= 0.0:
            raise ValueError(f"shortcut_distillation reflux ratio must be positive, got {reflux}")

        f_total = feed.molar_flow
        z_feed = feed.composition
        f_flows = {cid: y * f_total for cid, y in z_feed.items()}

        # 1. Key product flows from the recoveries.
        d_lk = recovery_lk * f_flows[lk]
        b_hk = recovery_hk * f_flows[hk]
        d_hk = f_flows[hk] - b_hk
        b_lk = f_flows[lk] - d_lk
        nonkeys = [cid for cid in z_feed if cid not in (lk, hk)]

        # 2. Preliminary non-key split: feed K above the heavy key goes overhead.
        k_feed = _feed_k(thermo, feed)
        d = {cid: (f_flows[cid] if k_feed.get(cid, 0.0) > k_feed[hk] else 0.0) for cid in nonkeys}

        # 3. Fenske fixed point on the non-key distribution. K-values for
        # components that vanish from a product phase carry over from the
        # previous iteration (seeded from the feed K), so the loop never
        # loses a component the incipient composition dropped.
        nmin = 0.0
        k_prev: tuple[dict[str, float], dict[str, float]] | None = None
        for _ in range(200):
            total_d = d_lk + d_hk + sum(d.values())
            total_b = f_total - total_d
            d_map = {**d, lk: d_lk, hk: d_hk}
            xd = {cid: d_map[cid] / total_d for cid in z_feed}
            xb = {cid: (f_flows[cid] - d_map[cid]) / total_b for cid in z_feed}
            _, k_top = (
                _dew_k(thermo, xd, p_top) if condenser == "partial" else _bubble_k(thermo, xd, p_top)
            )
            _, k_bottom = _bubble_k(thermo, xb, p_bottom)
            if k_prev is not None:
                k_top = {**k_prev[0], **k_top}
                k_bottom = {**k_prev[1], **k_bottom}
            k_prev = (k_top, k_bottom)
            if k_top.get(lk, 0.0) <= 0.0 or k_bottom.get(lk, 0.0) <= 0.0:
                raise ValueError("shortcut_distillation: thermo gives non-positive key K-values")
            alpha_lk = math.sqrt((k_top[lk] / k_top[hk]) * (k_bottom[lk] / k_bottom[hk]))
            nmin = fenske_nmin(alpha_lk, xd[lk], xd[hk], xb[lk], xb[hk])
            d_new = {}
            for cid in nonkeys:
                alpha_i = math.sqrt((k_top[cid] / k_top[hk]) * (k_bottom[cid] / k_bottom[hk]))
                ratio = alpha_i**nmin * (d_hk / b_hk)
                d_new[cid] = f_flows[cid] * ratio / (1.0 + ratio)
            delta = max(abs(d_new[cid] - d[cid]) for cid in nonkeys) if nonkeys else 0.0
            d = d_new
            if delta <= 1e-10 * f_total:
                break

        # 4. Underwood, Gilliland, Kirkbride. Underwood's root is on
        # heavy-key-relative alphas (alpha_HK = 1), not absolute K-values.
        total_d = d_lk + d_hk + sum(d.values())
        total_b = f_total - total_d
        d_map = {**d, lk: d_lk, hk: d_hk}
        xd = {cid: d_map[cid] / total_d for cid in z_feed}
        xb = {cid: (f_flows[cid] - d_map[cid]) / total_b for cid in z_feed}
        q = 1.0 - feed.vapor_fraction
        k_hk = k_feed[hk]
        alphas = {cid: k / k_hk for cid, k in k_feed.items()}
        theta = underwood_theta(alphas, z_feed, q)
        rmin = underwood_rmin(alphas, xd, theta)
        if rmin <= 0.0:
            raise ValueError(
                f"shortcut_distillation: Underwood Rmin is {rmin:.4g}; the key split is not "
                "feasible with these feed relative volatilities"
            )
        if params.get("R") is None:
            reflux = float(params["R_over_Rmin"]) * rmin
        stages = gilliland(reflux, rmin, nmin)
        kr = kirkbride(z_feed[hk], z_feed[lk], xb[lk], xd[hk], total_b / total_d)
        feed_stage = kr / (1.0 + kr) * stages

        # 5. Outlets and duties.
        t_sat_vap, _ = _dew_k(thermo, xd, p_top)
        t_sat_liq, _ = _bubble_k(thermo, xd, p_top)
        t_bottom, _ = _bubble_k(thermo, xb, p_bottom)
        h_top_vap = thermo.flash_pt(xd, t_sat_vap, p_top, 1.0).enthalpy
        h_top_liq = thermo.flash_pt(xd, t_sat_liq, p_top, 1.0).enthalpy
        reflux_flow = reflux * total_d
        vapour_top = reflux_flow + total_d
        duty_condenser_w = (h_top_vap - h_top_liq) * (
            vapour_top if condenser == "total" else reflux_flow
        )
        distillate = thermo.flash_pt(
            xd, t_sat_liq if condenser == "total" else t_sat_vap, p_top, total_d
        )
        bottoms = thermo.flash_pt(xb, t_bottom, p_bottom, total_b)
        h_in = feed.molar_flow * feed.enthalpy
        h_out = total_d * distillate.enthalpy + total_b * bottoms.enthalpy
        duty_reboiler_w = (h_out - h_in) + duty_condenser_w
        info = {
            "Nmin": nmin,
            "Rmin": rmin,
            "R": reflux,
            "N": stages,
            "feed_stage": feed_stage,
            "kirkbride_ratio": kr,
            "q": q,
            "D_molar_flow": total_d,
            "B_molar_flow": total_b,
            "duty_condenser_W": duty_condenser_w,
            "duty_reboiler_W": duty_reboiler_w,
        }
        return UnitResult(
            outlets={"distillate": distillate, "bottoms": bottoms},
            duty_W=duty_reboiler_w - duty_condenser_w,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Seader-Henley-Roper Examples 9.2-9.7 basis (pp. 350-360): the
        debutanizer feed, keys nC4/iC5 at the book's recoveries, total
        condenser at 80 psia, R/Rmin = 1.688."""
        feed_total = sum(_EXAMPLE_FEED_LBMOL_H.values())
        feeds = {
            "feed": {
                "T": _EXAMPLE_FEED_T,
                "P": _EXAMPLE_P,
                "molar_flow": feed_total * _LBMOL_H_TO_MOL_S,
                "composition": {cid: n / feed_total for cid, n in _EXAMPLE_FEED_LBMOL_H.items()},
            },
        }
        params = {
            "light_key": "nC4",
            "heavy_key": "iC5",
            "recovery_LK_D": _EXAMPLE_RECOVERY_LK_D,
            "recovery_HK_B": _EXAMPLE_RECOVERY_HK_B,
            "R_over_Rmin": _EXAMPLE_R_OVER_RMIN,
            "P_top": _EXAMPLE_P,
            "P_bottom": _EXAMPLE_P,
            "condenser": "total",
        }
        return feeds, params
