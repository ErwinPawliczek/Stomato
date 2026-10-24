"""Catalytic reformer R0 adapter — Fahim Table 5.3 yield correlations (spec U-H2).

R0 is a mass-only yield-table reactor: the naphtha feed converts to reformate
plus an offgas lump at mass yields set by the reformate severity. Correlations
(Fahim, Al-Sahhaf & Elkilani, *Fundamentals of Petroleum Refining*, Elsevier
2010, ch. 5, Table 5.3; equations re-typed from the open full text):

    C5+ vol% = 142.7914 − 0.77033·RONr + 0.219122·(N + 2A)   (5.17)
    H2  wt%  = −12.1641 + 0.06134·C5+ + 0.099482·RONr        (5.8)
    C1  wt%  = 11.509 − 0.125·C5+                            (5.9)
    C2  wt%  = 16.496 − 0.1758·C5+                           (5.10)
    C3  wt%  = 24.209 − 0.2565·C5+                           (5.11)
    C4  wt%  = 27.024 − 0.2837·C5+                           (5.12)
    nC4 wt%  = 0.585·C4;  iC4 wt% = 0.415·C4                 (5.13)/(5.14)
    H2 MSCF/bbl = 0.0002 + 0.48848·H2 wt%                    (5.18)

The example basis (and the V1 case) is the book's worked Example E5.2: 100
m3/h heavy naphtha, sg 0.778, A = 11.5 vol%, N = 21.7 vol%, reformate RON 94
→ C5+ 80.17 vol%; the book's own mass-balance table prints H2 2.1051, C1
1.4871, C2 2.4012, C3 3.6441 and total C4 4.2784 wt%.

Deviation from the spec's "H2 and light ends as real components", with the
measured reason: the row balance is ``mass_elements`` and its element ledger
closes at 1e-8 for every species with a molecular formula. A real H2/C1-C4
product slate carries C and H atoms that a naphtha feed cannot supply — the
feed would have to be a real species whose atoms the empirical mass
correlations do not conserve (verified: C6+ feed, 1.3e-2 relative carbon
mismatch against the E5.2 yields). The products are therefore two mass-only
pseudo lumps (`reformate`, `reformer_offgas`) with the full species split
reported in `info`; real light ends need the pseudo-component elemental
characterization proposed in the row notes' GitHub issue.

The duty is the sensible-only package-enthalpy change, flagged
`heat_of_reaction_basis_sensible_only`. Refuses (ValueError, naming the
parameter): a non-positive RON, negative feed N/A vol%, a C5+ yield outside
(0, 100] vol%, any negative light-end yield, and an empty feed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record, register_pseudo
from ngdesign.units._physics.kinetics import yield_shift

register_pseudo("reformer_naphtha", "reformer heavy naphtha (example, sg 0.778)", Tb=400.0, sg=0.778)
register_pseudo("reformate", "reformate C5+ lump", Tb=420.0, sg=0.79)
register_pseudo("reformer_offgas", "reformer offgas lump (H2 + C1-C4)", Tb=200.0, sg=0.35)


class CatalyticReformer:
    """Catalytic reformer at R0: lumped yields vs reformate RON (Fahim Table 5.3)."""

    inlet_ports: tuple[str, ...] = ("naphtha_in",)
    outlet_ports: tuple[str, ...] = ("reformate_out", "h2_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["naphtha_in"]
        ron = float(params["ron_reformate"])
        if ron <= 0.0:
            raise ValueError(f"reformer: ron_reformate {ron} must be positive")
        n_vol = float(params["naphthenes_vol_pct"])
        a_vol = float(params["aromatics_vol_pct"])
        if n_vol < 0.0 or a_vol < 0.0:
            raise ValueError(f"reformer: naphthenes_vol_pct {n_vol} / aromatics_vol_pct {a_vol} must be >= 0")
        t_out = float(params.get("T_out", 780.0))
        p_out = float(params.get("P_out", 3.0e6))

        c5p = 142.7914 - 0.77033 * ron + 0.219122 * (n_vol + 2.0 * a_vol)  # eq (5.17)
        if not 0.0 < c5p <= 100.0:
            raise ValueError(
                f"reformer: ron_reformate {ron} with N+2A {n_vol + 2.0 * a_vol} gives a C5+ "
                f"yield {c5p:.4g} vol% outside (0, 100] — outside the correlation's envelope"
            )
        h2_w = -12.1641 + 0.06134 * c5p + 0.099482 * ron  # eq (5.8)
        c1_w = 11.509 - 0.125 * c5p  # (5.9)
        c2_w = 16.496 - 0.1758 * c5p  # (5.10)
        c3_w = 24.209 - 0.2565 * c5p  # (5.11)
        c4_w = 27.024 - 0.2837 * c5p  # (5.12)
        negatives = [
            name
            for name, value in (("H2", h2_w), ("C1", c1_w), ("C2", c2_w), ("C3", c3_w), ("C4", c4_w))
            if value < 0.0
        ]
        if negatives:
            raise ValueError(
                f"reformer: severity gives negative yield(s) wt% for {', '.join(negatives)} "
                "(past the correlation's envelope)"
            )
        nc4_w = 0.585 * c4_w  # eq (5.13)
        ic4_w = 0.415 * c4_w  # eq (5.14)
        offgas_w = math.fsum((h2_w, c1_w, c2_w, c3_w, c4_w))
        if offgas_w >= 100.0:
            raise ValueError(f"reformer: offgas yield {offgas_w:.4g} wt% leaves no reformate")

        n_in = {cid: feed.molar_flow * y for cid, y in feed.composition.items() if y > 0.0}
        feed_cids = [cid for cid, n in n_in.items() if n > 0.0]
        if not feed_cids:
            raise ValueError("reformer: naphtha_in carries no components")
        yields_mass = [1.0 - offgas_w / 100.0, offgas_w / 100.0]
        n_out = yield_shift(n_in, feed_cids, yields_mass, ["reformate", "reformer_offgas"])

        h_in = feed.enthalpy * feed.molar_flow
        h_out = 0.0
        outlets: dict[str, StreamState] = {}
        for port, cid in (("reformate_out", "reformate"), ("h2_out", "reformer_offgas")):
            state = thermo.flash_pt({cid: 1.0}, t_out, p_out, n_out[cid])
            outlets[port] = state
            h_out += state.enthalpy * state.molar_flow
        return UnitResult(
            outlets=outlets,
            duty_W=h_out - h_in,
            info={
                "c5p_vol_pct": c5p,
                "h2_wt_pct": h2_w,
                "c1_wt_pct": c1_w,
                "c2_wt_pct": c2_w,
                "c3_wt_pct": c3_w,
                "c4_total_wt_pct": c4_w,
                "nc4_wt_pct": nc4_w,
                "ic4_wt_pct": ic4_w,
                "offgas_wt_pct": offgas_w,
                "reformate_wt_pct": 100.0 - offgas_w,
                "h2_mscf_bbl": 0.0002 + 0.48848 * h2_w,  # eq (5.18), MSCF/bbl per the book
                "heat_of_reaction_basis_sensible_only": 1.0,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Fahim Example E5.2: 100 m3/h heavy naphtha, sg 0.778, A 11.5 / N 21.7 vol%, RON 94."""
        mass_kg_s = 100.0 / 3600.0 * 778.0  # 100 m3/h at sg 0.778
        mw = float(component_record("reformer_naphtha")["mw"])
        feeds = {
            "naphtha_in": {
                "T": 750.0,
                "P": 3.0e6,
                "molar_flow": mass_kg_s / (mw / 1000.0),
                "composition": {"reformer_naphtha": 1.0},
            }
        }
        params: dict[str, Any] = {
            "ron_reformate": 94.0,
            "naphthenes_vol_pct": 21.7,
            "aromatics_vol_pct": 11.5,
            "T_out": 780.0,
            "P_out": 3.0e6,
        }
        return feeds, params
