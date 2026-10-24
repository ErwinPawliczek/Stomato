"""Reboiled stripper, R0 (spec U-E).

Plugin kind "unit", name "reboiled_stripper". Ports feed -> overhead +
bottoms. Method (spec): the Kremser stripping group method per component at
R0 — the liquid feed flows down N ideal stages against a stripping vapour of
size given in params; the fraction stripped is ``kremser_fraction(S_i, N)``
with ``S_i = K_i*V/L``, eqs. (5-48)/(5-50) evaluated in the stripping form.
The stripping agent (steam, boilup vapour, nitrogen) is the params flow, not
a stream port, so its own amount appears only through V and not in the
component balance; the model is isothermal at the feed state and its duty
reports the enthalpy change (documented simplifications of an R0 model).

K-values come from ``thermo.k_values`` at the feed state; params
``k_overrides`` (``{cid: K}``) replaces them per component — the documented
route for reference cases whose basis is the book's back-solved stripping
factors. Raises typed ValueErrors on a bad ``N``, a non-positive vapour
flow, or a missing K.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column_shortcut._kremser import two_feed_split

#: Seader-Henley Example 9.8 basis (pp. 371-372), used as the adapter's
#: example case: 120 lbmol/h of a rich solvent (SO2, butadiene isomers and a
#: butadiene-sulfone stand-in) stripped at 300 K / 101325 Pa by 94.3 lbmol/h
#: of nitrogen across 3 ideal stages. The back-solved K-values reproduce the
#: printed unrecovered fractions (see the V1 case).
_EXAMPLE_FEED_LBMOL_H = {
    "SO2": 10.0,
    "1,3-butadiene": 8.0,
    "1,2-butadiene": 2.0,
    "n-decane": 100.0,  # stand-in for butadiene sulfone
}
_EXAMPLE_T = 300.0
_EXAMPLE_P = 101325.0
_EXAMPLE_N = 3.0
_EXAMPLE_VAPOUR_LBMOL_H = 94.3
_EXAMPLE_K = {"SO2": 6.96, "1,3-butadiene": 4.53, "1,2-butadiene": 3.01, "n-decane": 0.0162}

#: lbmol/h -> mol/s (0.45359237 kmol per lbmol, 3600 s per h).
_LBMOL_H_TO_MOL_S = 0.45359237 / 3.6


class ReboiledStripper:
    """Kremser reboiled stripper (feed-determined), R0: balances plus a stage
    and boilup spec."""

    inlet_ports = ("feed",)
    outlet_ports = ("overhead", "bottoms")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ValueError("stripper needs a feed inlet stream")
        if feed.molar_flow <= 0.0:
            raise ValueError("stripper feed flow must be positive")
        if "N" not in params:
            raise ValueError("stripper requires the 'N' parameter (ideal stages)")
        if "vapour_flow" not in params:
            raise ValueError(
                "stripper requires the 'vapour_flow' parameter (mol/s of stripping vapour)"
            )
        stages = float(params["N"])
        vapour = float(params["vapour_flow"])
        if stages <= 0.0:
            raise ValueError(f"stripper N must be positive, got {stages}")
        if vapour <= 0.0:
            raise ValueError(f"stripper vapour_flow must be positive, got {vapour}")
        overrides = params.get("k_overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("stripper k_overrides must be a {cid: K} mapping")

        k_map: dict[str, float]
        if overrides:
            k_map = {str(cid): float(k) for cid, k in overrides.items()}
            for cid, k in k_map.items():
                if k <= 0.0:
                    raise ValueError(f"stripper k_overrides[{cid}] must be positive, got {k}")
        else:
            package_ks = thermo.k_values(feed.composition, feed.T, feed.P)
            if package_ks is None:
                raise ValueError(
                    "stripper: thermo gives no K-values at the feed condition "
                    f"({feed.T:.2f} K, {feed.P:.0f} Pa); pass k_overrides"
                )
            k_map = package_ks

        liquid_flows = {cid: y * feed.molar_flow for cid, y in feed.composition.items()}
        # No gas-feed port: the stripping agent is the params vapour_flow.
        overhead_flows, bottoms_flows = two_feed_split(
            {}, liquid_flows, k_map, feed.molar_flow, vapour, stages
        )
        total_overhead = sum(overhead_flows.values())
        total_bottoms = sum(bottoms_flows.values())
        overhead = thermo.flash_pt(
            {cid: n / total_overhead for cid, n in overhead_flows.items()},
            feed.T,
            feed.P,
            total_overhead,
        )
        bottoms = thermo.flash_pt(
            {cid: n / total_bottoms for cid, n in bottoms_flows.items()},
            feed.T,
            feed.P,
            total_bottoms,
        )

        info: dict[str, float] = {}
        for cid in sorted(liquid_flows):
            info[f"overhead_{cid}"] = overhead_flows[cid]
            info[f"bottoms_{cid}"] = bottoms_flows[cid]
        duty_w = (
            total_overhead * overhead.enthalpy
            + total_bottoms * bottoms.enthalpy
            - feed.molar_flow * feed.enthalpy
        )
        return UnitResult(
            outlets={"overhead": overhead, "bottoms": bottoms},
            duty_W=duty_w,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Seader-Henley-Roper Example 9.8 basis (pp. 371-372): rich solvent
        stripped by nitrogen, N = 3, with K-values back-solved from the
        printed unrecovered fractions. The butadiene-sulfone component is the
        documented ``n-decane`` stand-in."""
        feed_total = sum(_EXAMPLE_FEED_LBMOL_H.values())
        feeds = {
            "feed": {
                "T": _EXAMPLE_T,
                "P": _EXAMPLE_P,
                "molar_flow": feed_total * _LBMOL_H_TO_MOL_S,
                "composition": {cid: n / feed_total for cid, n in _EXAMPLE_FEED_LBMOL_H.items()},
            },
        }
        params = {
            "N": _EXAMPLE_N,
            "vapour_flow": _EXAMPLE_VAPOUR_LBMOL_H * _LBMOL_H_TO_MOL_S,
            "k_overrides": dict(_EXAMPLE_K),
        }
        return feeds, params
