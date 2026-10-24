"""Liquid-liquid extractor, R0 (spec U-E).

Plugin kind "unit", name "liquid_liquid_extractor". Ports feed + solvent_in
-> raffinate + extract. Method (spec): the Kremser extraction form per
component at R0 — ``E_i = K_D,i * S/F`` where ``S`` and ``F`` are the
solvent-side and feed-side carrier flows (each port total minus its solute
content, the dilute-solute basis of the book's examples); the fraction
extracted is ``kremser_fraction(E_i, N)`` with ``N`` given in params.
Distribution coefficients come from params ``K_D`` (``{cid: K_D}``; the
absorber's ``k_overrides`` name is accepted as an alias — passing both is
refused) or from the package's ``k_values`` — which the registered packages return as None
when they describe no second liquid phase, and the adapter refuses in that
case per the spec. Components that are not solutes are immiscible at R0:
each goes wholly with its own inlet phase. Outlets flash at their inlet
port's state; the duty reports the enthalpy change (isothermal R0).

Raises typed ValueErrors on a bad ``N``, a non-positive ``K_D``, a missing
coefficient for a solute, or a package without liquid-liquid K-values.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column_shortcut._kremser import two_feed_split

#: Seader-Henley Example 5.2 basis (pp. 183-185), used as the adapter's
#: example case: 4,536 kg/h of p-dioxane (25 wt%) and water extracted by
#: 6,804 kg/h of benzene; the book's constant mass-ratio coefficient K'D =
#: 1.2 converts to the adapter's mole-ratio basis K_D = K'D x MW_benzene /
#: MW_water = 1.2 x 78.11 / 18.015 = 5.2027, giving E = K_D x S/F = 2.399
#: and N = 2 stages -> the book's 89.1 % extraction (89.08 % computed).
_EXAMPLE_FEED_KMOL_H = {"p-dioxane": 12.871, "water": 188.840}
_EXAMPLE_SOLVENT_KMOL_H = {"benzene": 87.085}
_EXAMPLE_T = 298.15
_EXAMPLE_P = 101325.0
_EXAMPLE_N = 2.0
_EXAMPLE_KD = {"p-dioxane": 5.2027}


class LiquidLiquidExtractor:
    """Kremser liquid-liquid extractor (feed-determined), R0: balances plus a
    stage spec."""

    inlet_ports = ("feed", "solvent_in")
    outlet_ports = ("raffinate", "extract")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets.get("feed")
        solvent = inlets.get("solvent_in")
        if feed is None or solvent is None:
            raise ValueError("extractor needs feed and solvent_in inlet streams")
        if feed.molar_flow <= 0.0 or solvent.molar_flow <= 0.0:
            raise ValueError("extractor inlet flows must both be positive")
        if "N" not in params:
            raise ValueError("extractor requires the 'N' parameter (ideal stages)")
        stages = float(params["N"])
        if stages <= 0.0:
            raise ValueError(f"extractor N must be positive, got {stages}")
        given_kd = params.get("K_D")
        k_overrides = params.get("k_overrides")
        if given_kd is not None and k_overrides is not None:
            raise ValueError(
                "extractor accepts one distribution-coefficient param name: give 'K_D' "
                "or 'k_overrides', not both"
            )
        given_kd = given_kd if given_kd is not None else (k_overrides or {})
        if given_kd and not isinstance(given_kd, dict):
            raise ValueError("extractor K_D must be a {cid: distribution coefficient} mapping")
        if given_kd:
            k_map = {str(cid): float(k) for cid, k in given_kd.items()}
        else:
            # Spec default: the package's k_values, refused when the package
            # describes no second liquid phase (k_values returns None).
            package_ks = thermo.k_values(feed.composition, feed.T, feed.P)
            if package_ks is None:
                raise ValueError(
                    "extractor: package thermo gives no second liquid phase at the feed "
                    f"condition ({feed.T:.2f} K, {feed.P:.0f} Pa); pass K_D in params"
                )
            k_map = package_ks
        for cid, k in k_map.items():
            if k <= 0.0:
                raise ValueError(f"extractor distribution coefficient for {cid!r} must be positive, got {k}")

        feed_flows = {cid: y * feed.molar_flow for cid, y in feed.composition.items()}
        solvent_flows = {cid: y * solvent.molar_flow for cid, y in solvent.composition.items()}
        solutes = set(k_map)
        if not solutes <= (set(feed_flows) | set(solvent_flows)):
            missing = solutes - (set(feed_flows) | set(solvent_flows))
            raise ValueError(f"extractor K_D names components absent from the feeds: {sorted(missing)}")

        f_carrier = feed.molar_flow - sum(feed_flows.get(cid, 0.0) for cid in solutes)
        s_carrier = solvent.molar_flow - sum(solvent_flows.get(cid, 0.0) for cid in solutes)
        if f_carrier <= 0.0 or s_carrier <= 0.0:
            raise ValueError("extractor carrier flows must both be positive on the dilute basis")
        solute_feed = {cid: feed_flows.get(cid, 0.0) for cid in solutes}
        solute_solvent = {cid: solvent_flows.get(cid, 0.0) for cid in solutes}
        extract_solutes, raffinate_solutes = two_feed_split(
            solute_solvent, solute_feed, k_map, f_carrier, s_carrier, stages
        )
        extract_flows = {
            cid: (extract_solutes.get(cid, 0.0) if cid in solutes else solvent_flows.get(cid, 0.0))
            for cid in set(solvent_flows) | solutes
        }
        raffinate_flows = {
            cid: (raffinate_solutes.get(cid, 0.0) if cid in solutes else feed_flows.get(cid, 0.0))
            for cid in set(feed_flows) | solutes
        }
        total_extract = sum(extract_flows.values())
        total_raffinate = sum(raffinate_flows.values())
        extract = thermo.flash_pt(
            {cid: n / total_extract for cid, n in extract_flows.items()},
            solvent.T,
            solvent.P,
            total_extract,
        )
        raffinate = thermo.flash_pt(
            {cid: n / total_raffinate for cid, n in raffinate_flows.items()},
            feed.T,
            feed.P,
            total_raffinate,
        )

        info: dict[str, float] = {}
        for cid in sorted(solutes):
            info[f"extract_{cid}"] = extract_flows[cid]
            info[f"raffinate_{cid}"] = raffinate_flows[cid]
            info[f"extraction_fraction_{cid}"] = extract_flows[cid] / (
                extract_flows[cid] + raffinate_flows[cid]
            )
        duty_w = (
            total_extract * extract.enthalpy
            + total_raffinate * raffinate.enthalpy
            - feed.molar_flow * feed.enthalpy
            - solvent.molar_flow * solvent.enthalpy
        )
        return UnitResult(
            outlets={"raffinate": raffinate, "extract": extract},
            duty_W=duty_w,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Seader-Henley Example 5.2 basis (pp. 183-185): p-dioxane extracted
        from water by benzene at the book's mass-ratio K'D = 1.2 converted to
        the mole basis (K_D = 5.2027), N = 2 stages, 89.1 % extraction."""
        feeds = {
            "feed": {
                "T": _EXAMPLE_T,
                "P": _EXAMPLE_P,
                "molar_flow": sum(_EXAMPLE_FEED_KMOL_H.values()),
                "composition": {
                    cid: n / sum(_EXAMPLE_FEED_KMOL_H.values()) for cid, n in _EXAMPLE_FEED_KMOL_H.items()
                },
            },
            "solvent_in": {
                "T": _EXAMPLE_T,
                "P": _EXAMPLE_P,
                "molar_flow": sum(_EXAMPLE_SOLVENT_KMOL_H.values()),
                "composition": {
                    cid: n / sum(_EXAMPLE_SOLVENT_KMOL_H.values())
                    for cid, n in _EXAMPLE_SOLVENT_KMOL_H.items()
                },
            },
        }
        params = {"N": _EXAMPLE_N, "K_D": dict(_EXAMPLE_KD)}
        return feeds, params
