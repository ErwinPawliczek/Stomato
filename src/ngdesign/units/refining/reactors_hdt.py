"""Naphtha hydrotreater R0 adapter — Fahim E12.2 reaction slate (spec U-H2).

R0 is a stoichiometric hydrotreater over model compounds: sulfur removal and
nitrogen removal are declared as removal fractions (not kinetics), and
olefin/aromatic saturation as conversions. The reaction slate (Fahim,
Al-Sahhaf & Elkilani, *Fundamentals of Petroleum Refining*, Elsevier 2010,
worked Example E12.2 (p. 309) and the pyridine HDN reaction of the ch. 7
hydroconversion scheme (7.1) (p. 156), re-typed from the open full text):

    thiophene  + 4 H2 -> nC4 + H2S          (E12.2.1, HDS)
    pyridine   + 5 H2 -> nC5 + NH3          (scheme (7.1), p. 156, HDN)
    1-pentene  + 1 H2 -> nC5                (E12.2.2, olefin saturation)
    benzene    + 3 H2 -> cyclohexane        (E12.2.3, aromatic saturation)

Sulfur rides on `thiophene` and nitrogen on `pyridine` (the R0 slate's only
heteroatom carriers — naphtha sulfur is predominantly thiophenic at this
level); a feed's other species pass through. Unreacted H2, H2S and NH3 leave
on `gas_out`; everything else on `treated_out`. The paraffin cracking
reaction of E12.2.4 is out of scope: hydrocracking is not hydrotreating
chemistry, and the example's H2 demand excludes it.

The duty is the sensible-only package-enthalpy change, flagged
`heat_of_reaction_basis_sensible_only` — the R0 slate carries no reaction
enthalpies, so the duty is not a heat of reaction. `info` reports per-species
production/consumption in mol/s, the feed's S/N wt% (IUPAC 2021 standard
atomic weights S 32.06, N 14.007), and Maples's hydrogen make-up estimate
191·S − 30.7 scf/bbl (S = feed sulfur wt%; Maples, *Petroleum Refinery
Process Economics*, 2nd ed. 2000, p. 16, as reproduced in Colorado School of
Mines course notes) — reported raw, never clamped: below ~0.16 wt% S it goes
negative because the correlation is a make-up estimate fitted on refinery
feeds, not a stoichiometric demand.

Refuses (ValueError, naming the parameter): a removal fraction or conversion
outside [0, 1], a hydrogen feed short of the stoichiometric demand (beyond a
1e-9 relative slack), and a solution whose `gas_out` port would be empty
(its species are all zero — give hydrogen excess or S/N removal).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record, register_pseudo
from ngdesign.units._physics.kinetics import yield_shift

register_pseudo("hdt_naphtha", "hydrotreater naphtha lump (inert)", Tb=400.0, sg=0.74)

#: Species routed to `gas_out`; everything else leaves on `treated_out`.
_GAS_CIDS: frozenset[str] = frozenset({"H2", "H2S", "NH3"})

#: IUPAC 2021 standard atomic weights (g/mol), for the S/N wt% info keys.
AW_SULFUR = 32.06
AW_NITROGEN = 14.007


def _frac(params: Mapping[str, Any], key: str, default: float) -> float:
    """A removal fraction or conversion in [0, 1]; refuses anything else."""
    value = float(params.get(key, default))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"naphtha_ht: {key} {value} outside [0, 1]")
    return value


class NaphthaHydrotreater:
    """Naphtha hydrotreater at R0: model-compound HDS/HDN and saturation."""

    inlet_ports: tuple[str, ...] = ("naphtha_in", "h2_in")
    outlet_ports: tuple[str, ...] = ("treated_out", "gas_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        f_s = _frac(params, "sulfur_removal_frac", 1.0)
        f_n = _frac(params, "nitrogen_removal_frac", 1.0)
        f_pent = _frac(params, "pentene_conversion", 0.0)
        f_bz = _frac(params, "benzene_conversion", 0.0)
        t_out = float(params.get("T_out", 620.0))
        p_out = float(params.get("P_out", 3.0e6))

        # Combined inlet moles (both ports are mixed into one reaction space).
        n_mix: dict[str, float] = {}
        for port in ("naphtha_in", "h2_in"):
            for cid, y in inlets[port].composition.items():
                n_mix[cid] = n_mix.get(cid, 0.0) + y * inlets[port].molar_flow
        n_thio = n_mix.get("thiophene", 0.0)
        n_py = n_mix.get("pyridine", 0.0)
        n_pent = n_mix.get("1-pentene", 0.0)
        n_bz = n_mix.get("benzene", 0.0)
        n_h2 = n_mix.get("H2", 0.0)

        # Reacted shares, per the E12.2 slate.
        n_thio_r = n_thio * f_s
        n_py_r = n_py * f_n
        n_pent_r = n_pent * f_pent
        n_bz_r = n_bz * f_bz
        h2_needed = 4.0 * n_thio_r + 5.0 * n_py_r + n_pent_r + 3.0 * n_bz_r
        if h2_needed > n_h2 + 1e-9 * max(1.0, n_h2):
            raise ValueError(
                f"naphtha_ht: hydrogen feed {n_h2} mol/s is short of the stoichiometric demand "
                f"{h2_needed} mol/s (4·HDS + 5·HDN + 1·olefin + 3·aromatic) — raise the h2_in "
                "molar flow or lower the removal/conversion parameters"
            )

        # Mass basis for the yield shift: a species whose reacted share is
        # positive has its FULL feed amount consumed (its unreacted remainder
        # re-enters as a product mass — yield_shift is closed-world, so the
        # re-added remainder must be part of the consumed mass); a species
        # with no reacted share passes through untouched.
        feed_cids: list[str] = []
        for cid, n_feed in (
            ("thiophene", n_thio if n_thio_r > 0.0 else 0.0),
            ("pyridine", n_py if n_py_r > 0.0 else 0.0),
            ("1-pentene", n_pent if n_pent_r > 0.0 else 0.0),
            ("benzene", n_bz if n_bz_r > 0.0 else 0.0),
            ("H2", n_h2 if h2_needed > 0.0 else 0.0),
        ):
            if n_feed > 0.0:
                n_mix[cid] = n_feed
                feed_cids.append(cid)
        if not feed_cids:
            raise ValueError("naphtha_ht: no removal/conversion requested — nothing to solve")
        mols = {cid: float(component_record(cid)["mw"]) for cid in set(feed_cids) | _GAS_CIDS}
        mols.update(
            {cid: float(component_record(cid)["mw"]) for cid in ("nC4", "nC5", "cyclohexane", "hdt_naphtha")}
        )
        consumed_mass = math.fsum(n_mix[cid] * mols[cid] for cid in feed_cids)
        products: list[str] = []
        yields_mass: list[float] = []

        def _add(cid: str, moles: float) -> None:
            if moles > 0.0:
                products.append(cid)
                yields_mass.append(moles * mols[cid] / consumed_mass)

        _add("nC4", n_thio_r)
        _add("H2S", n_thio_r)
        _add("nC5", n_py_r + n_pent_r)
        _add("NH3", n_py_r)
        _add("cyclohexane", n_bz_r)
        if h2_needed > 0.0:
            _add("H2", n_h2 - h2_needed)
        for cid, n_total, n_r in (
            ("thiophene", n_thio, n_thio_r),
            ("pyridine", n_py, n_py_r),
            ("1-pentene", n_pent, n_pent_r),
            ("benzene", n_bz, n_bz_r),
        ):
            if n_r > 0.0:
                _add(cid, n_total - n_r)  # unremoved remainder of a consumed species
        n_out = yield_shift(n_mix, feed_cids, yields_mass, products)

        # Partition the shifted mixture to the ports and flash at outlet T/P.
        gas_cids = sorted(cid for cid in _GAS_CIDS if n_out.get(cid, 0.0) > 0.0)
        treated_cids = sorted(cid for cid, n in n_out.items() if n > 0.0 and cid not in _GAS_CIDS)
        if not gas_cids:
            raise ValueError(
                "naphtha_ht: gas_out would carry no species (no H2 excess, no H2S/NH3 formed) — "
                "give hydrogen excess or S/N removal"
            )
        n_gas = math.fsum(n_out[cid] for cid in gas_cids)
        n_treated = math.fsum(n_out[cid] for cid in treated_cids)
        h_in = math.fsum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out = 0.0
        outlets: dict[str, StreamState] = {}
        for port, cids, total in (
            ("treated_out", treated_cids, n_treated),
            ("gas_out", gas_cids, n_gas),
        ):
            z = {cid: n_out[cid] / total for cid in cids}
            state = thermo.flash_pt(z, t_out, p_out, total)
            outlets[port] = state
            h_out += state.enthalpy * state.molar_flow

        feed_mass = math.fsum(
            y * s.molar_flow * float(component_record(cid)["mw"])
            for s in inlets.values()
            for cid, y in s.composition.items()
        )
        sulfur_w = 100.0 * n_thio * AW_SULFUR / feed_mass
        nitrogen_w = 100.0 * n_py * AW_NITROGEN / feed_mass
        return UnitResult(
            outlets=outlets,
            duty_W=h_out - h_in,
            info={
                "h2_consumed_mol_s": h2_needed,
                "h2s_mol_s": n_thio_r,
                "nh3_mol_s": n_py_r,
                "nbutane_mol_s": n_thio_r,
                "npentane_mol_s": n_py_r + n_pent_r,
                "cyclohexane_mol_s": n_bz_r,
                "feed_sulfur_wt_pct": sulfur_w,
                "feed_nitrogen_wt_pct": nitrogen_w,
                "h2_makeup_maples_scf_bbl": 191.0 * sulfur_w - 30.7,
                "heat_of_reaction_basis_sensible_only": 1.0,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Defined basis: light naphtha lump with thiophene/pyridine/olefin/aromatic impurities.

        ~0.27 wt% sulfur (at the Maples correlation's useful end), 1.3x the
        R0-slate stoichiometric hydrogen, full S/N removal by default.
        """
        n_lump, n_thio, n_py, n_pent, n_bz = 97.0, 1.0, 0.01, 2.0, 3.0  # mol/s
        h2_feed = 1.3 * (4.0 * n_thio + 5.0 * n_py)
        total = n_lump + n_thio + n_py + n_pent + n_bz
        feeds = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3.0e6,
                "molar_flow": total,
                "composition": {
                    "hdt_naphtha": n_lump / total,
                    "thiophene": n_thio / total,
                    "pyridine": n_py / total,
                    "1-pentene": n_pent / total,
                    "benzene": n_bz / total,
                },
            },
            "h2_in": {
                "T": 600.0,
                "P": 3.0e6,
                "molar_flow": h2_feed,
                "composition": {"H2": 1.0},
            },
        }
        params: dict[str, Any] = {
            "sulfur_removal_frac": 1.0,
            "nitrogen_removal_frac": 1.0,
            "pentene_conversion": 0.0,
            "benzene_conversion": 0.0,
            "T_out": 620.0,
            "P_out": 3.0e6,
        }
        return feeds, params
