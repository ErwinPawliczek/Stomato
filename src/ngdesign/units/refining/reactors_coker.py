"""Delayed coker R0 adapter — Gary–Handwerk CCR yield table (spec U-H2).

R0 is a mass-only yield-table reactor: the residue feed cracks to coker gas,
naphtha, light/heavy gas oil and coke at mass yields correlated against the
feed's Conradson carbon residue (CCR). Yield correlations (Gary, Handwerk &
Kaiser, *Petroleum Refining: Technology and Economics*, 5th ed., ch. 5; as
reproduced in J. Jechura, "Delayed Coking Example", Colorado School of Mines
course notes, rev. January 26, 2016):

    coke wt%     = 1.6 · CCR
    gas wt%      = 7.8 + 0.144 · CCR
    gasoline wt% = 11.29 + 0.343 · CCR
    gas oil wt%  = 100 − coke − gas − gasoline

The example basis is the Jechura notes' worked-example feed: vacuum residuum,
40,000 bbl/day, 9.5 °API, 13.5 wt% CCR (no published worked *result* table
exists in open sources; the V1 case anchors the equations themselves).

Products are mass-only pseudo lumps (`coker_gas`, `coker_naphtha`,
`coker_lgo`, `coker_hgo`, `coke`) registered at import. Rationale: the row
balance is ``mass_elements`` and its element ledger tracks atoms only for
species with a molecular formula; a pseudo feed carries no atom sources, so
real reaction products would leave with atoms that never entered. The gas
lump hides the published coker-gas composition (G&H Table 5.8: H2 13.7, CO2
0.2, CH4 51.4, C2H4 1.5, C2H6 15.9, C3H6 3.1, C3H8 8.2, C4= 2.4, iC4 1.0,
nC4 2.6 mol%); splitting it into real species needs the pseudo-component
elemental characterization proposed in the row notes' GitHub issue.

The LGO/HGO split of the single published gas-oil yield is a configuration
spec (`gasoil_lgo_fraction`), not a correlation constant. The duty is the
sensible-only package-enthalpy change (outlets − inlets), flagged
`heat_of_reaction_basis_sensible_only` — the pseudo lumps carry no formation
enthalpy, so the duty is not a heat of reaction. Refuses (ValueError, naming
the parameter): a non-positive CCR, a CCR past the correlation envelope
(negative gas-oil yield), a gas-oil split outside (0, 1), and an empty feed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record, register_pseudo
from ngdesign.units._physics.kinetics import yield_shift

register_pseudo("coker_vacresid", "delayed-coker vacuum residuum (example)", Tb=1050.0, sg=1.00355)
register_pseudo("coker_gas", "coker gas lump (H2/CO2/C1-C4)", Tb=220.0, sg=0.45)
register_pseudo("coker_naphtha", "coker naphtha lump", Tb=420.0, sg=0.74)
register_pseudo("coker_lgo", "coker light gas oil lump", Tb=560.0, sg=0.84)
register_pseudo("coker_hgo", "coker heavy gas oil lump", Tb=700.0, sg=0.90)
register_pseudo("coke", "petroleum coke lump (mass only)", Tb=1100.0, sg=0.95)

#: 1 barrel = 42 US gallons, exactly (1959-inch definition, 1 gal = 3.785411784 L).
BBL_TO_M3 = 0.158987294928
#: Seconds per day.
DAY_S = 86400.0
#: Reference water density at 60 °F (the °API basis), kg/m3 — scales the
#: example feed only; no asserted number depends on it.
WATER_60F_KG_M3 = 999.0

#: Port -> product-lump wiring of the five coker outlets.
_PORT_LUMP: tuple[tuple[str, str], ...] = (
    ("gas_out", "coker_gas"),
    ("naphtha_out", "coker_naphtha"),
    ("lgo_out", "coker_lgo"),
    ("hgo_out", "coker_hgo"),
    ("coke_out", "coke"),
)


class DelayedCoker:
    """Delayed coker at R0: mass yields vs feed CCR (Gary–Handwerk)."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("gas_out", "naphtha_out", "lgo_out", "hgo_out", "coke_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["feed_in"]
        ccr = float(params["ccr_wt_pct"])
        if ccr <= 0.0:
            raise ValueError(f"coker: ccr_wt_pct {ccr} must be positive (the correlation basis)")
        f_lgo = float(params.get("gasoil_lgo_fraction", 0.5))
        if not 0.0 < f_lgo < 1.0:
            raise ValueError(f"coker: gasoil_lgo_fraction {f_lgo} outside (0, 1)")
        t_out = float(params.get("T_out", 773.15))
        p_out = float(params.get("P_out", 4.0e5))

        y_coke = 1.6 * ccr  # wt%, Gary–Handwerk ch. 5
        y_gas = 7.8 + 0.144 * ccr
        y_naphtha = 11.29 + 0.343 * ccr
        y_gasoil = 100.0 - math.fsum((y_coke, y_gas, y_naphtha))
        if y_gasoil <= 0.0:
            raise ValueError(
                f"coker: ccr_wt_pct {ccr} is past the correlation envelope "
                f"(gas-oil yield {y_gasoil:.4g} wt% would be negative)"
            )

        n_in = {cid: feed.molar_flow * y for cid, y in feed.composition.items() if y > 0.0}
        feed_cids = [cid for cid, n in n_in.items() if n > 0.0]
        if not feed_cids:
            raise ValueError("coker: feed_in carries no components")
        yields_mass = [
            y_gas / 100.0,
            y_naphtha / 100.0,
            (1.0 - f_lgo) * y_gasoil / 100.0,
            f_lgo * y_gasoil / 100.0,
            y_coke / 100.0,
        ]
        n_out = yield_shift(n_in, feed_cids, yields_mass, [lump for _, lump in _PORT_LUMP])

        h_in = feed.enthalpy * feed.molar_flow
        h_out = 0.0
        outlets: dict[str, StreamState] = {}
        for port, lump in _PORT_LUMP:
            n = n_out[lump]
            state = thermo.flash_pt({lump: 1.0}, t_out, p_out, n)
            outlets[port] = state
            h_out += state.enthalpy * state.molar_flow
        return UnitResult(
            outlets=outlets,
            duty_W=h_out - h_in,
            info={
                "coke_wt_pct": y_coke,
                "gas_wt_pct": y_gas,
                "naphtha_wt_pct": y_naphtha,
                "gasoil_wt_pct": y_gasoil,
                "lgo_wt_pct": (1.0 - f_lgo) * y_gasoil,
                "hgo_wt_pct": f_lgo * y_gasoil,
                "heat_of_reaction_basis_sensible_only": 1.0,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The Jechura notes' worked-example feed: vac resid 40,000 bpd, 9.5 °API, 13.5 CCR."""
        sg = 141.5 / (131.5 + 9.5)  # °API -> specific gravity (ASTM D1250 relation)
        mass_kg_s = 40000.0 * BBL_TO_M3 * sg * WATER_60F_KG_M3 / DAY_S
        mw = float(component_record("coker_vacresid")["mw"])
        feeds = {
            "feed_in": {
                "T": 770.0,
                "P": 4.0e5,
                "molar_flow": mass_kg_s / (mw / 1000.0),
                "composition": {"coker_vacresid": 1.0},
            }
        }
        params: dict[str, Any] = {
            "ccr_wt_pct": 13.5,
            "gasoil_lgo_fraction": 0.5,
            "T_out": 773.15,
            "P_out": 4.0e5,
        }
        return feeds, params
