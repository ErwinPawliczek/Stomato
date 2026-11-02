"""Catalytic reformer R1: Smith four-reaction kinetics in adiabatic beds (``specs/backend/units/reformer_cat.md``).

Smith, Chem. Eng. Prog. 55(6) (1959) 76-80.  The lumps are representative real C7
species, so every reaction is element-balanced with a real heat of reaction: P = nC7,
N = methylcyclohexane, A = toluene, and the light ends C1..nC5 split equally on moles.

    dehydro   N <-> A + 3 H2                         r1 = k1*(p_N - p_A*p_H**3/K1)
    n_to_p    N + H2 <-> P                           r2 = k2*(p_N*p_H - p_P/K2)
    hc_n      N + 7/3 H2 -> 7/15 (C1 + ... + nC5)    r3 = k3*p_N/P
    hc_p      P + 4/3 H2 -> 7/15 (C1 + ... + nC5)    r4 = k4*p_P/P

Rates are per kg catalyst in partial pressures (atm).  Each becomes a contract PowerLaw
on the mole-fraction basis at the bed's pressure, with p_i = y_i*P_atm folded into k0,
and the equilibrium term an explicit reverse rate: with K = exp(A_K - B_K/T),
k/K = k0*exp(-A_K)*exp(-(Ea - R*B_K)/(R*T)).

The constants are a required explicit input.  The ``smith1959`` preset stays refused:
the paper itself could not be read, and the one open reproduction found (Liang, Guo &
Pan, J. Zhejiang Univ. Sci. B 6(6) (2005) 590-596, eqs. 9-17, rate forms via Rase 1977)
prints k_p2 = 9.87*exp(35.98 - 59600/(1.8T)) with units kmol/(h kg_cat MPa**2), where the
atm-to-MPa factor for a second-order rate would be 97.4, not 9.87.  That tenfold doubt is
not resolved by guessing.  Its K1 and K2 are self-consistent (1.04e-3 = 0.101325**3 and
9.87 = 1/0.101325), but one constant short of a set is not a preset.

Beds are adiabatic with a fired interheater before each, on the pfr integrator, with
V_b = W_b/rho_b and no pressure drop.  The split is sharp and ideal.  R1 is a different
model from R0's yield correlation, so no parameter limit reproduces R0.  All SI.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw, PowerLawRate, Reaction, ReactionSet
from ngdesign.data import component_record
from ngdesign.units._physics.kinetics import R, apply_extents
from ngdesign.units.balance import stream_enthalpy
from ngdesign.units.reactors._shared import thermal_outlet
from ngdesign.units.reactors.plug_flow import integrate_plug_flow

NAPHTHENE, PARAFFIN, AROMATIC, HYDROGEN = "methylcyclohexane", "nC7", "toluene", "H2"
_LIGHTS = ("C1", "C2", "C3", "nC4", "nC5")
_SLATE = (NAPHTHENE, PARAFFIN, AROMATIC, HYDROGEN, *_LIGHTS)
_TO_H2_OUT = frozenset({HYDROGEN, "C1", "C2", "C3", "nC4"})

_RATE_UNITS = "mol/(kg_cat·s)"

#: lb-mol/(h lb_cat) to mol/(kg_cat s).
_C_U = 1000.0 / 3600.0

#: Pa per atm.
_PA_PER_ATM = 101325.0

_REVERSIBLE = ("dehydro", "n_to_p")
_IRREVERSIBLE = ("hc_n", "hc_p")


class ReformerKineticError(ValueError):
    """A refused reformer R1 specification; the message names the parameter."""


def _fold_pressure(k0: float, order: float, p_atm: float) -> float:
    """k0 per atm**order to a mole-fraction k0: p_i = y_i*P_atm folds in P_atm**order."""
    return float(k0 * p_atm**order)


def _smith_to_contract(k0: float, b_rankine: float, order: float, p_atm: float) -> tuple[float, float]:
    """(k0', Ea) of a rate in Smith's units, for a set quoted as Smith printed it.

    k0 in lb-mol/(h lb_cat atm**order) converts by 1000/3600 to mol/(kg_cat s); the
    pressure folds by P_atm**order; an exponent b/T[R] is (b/1.8)/T[K], so Ea = R*b/1.8.
    """
    return _fold_pressure(k0 * _C_U, order, p_atm), R * b_rankine / 1.8


def _law(forward: float, ea: float, orders: dict[str, float], reverse: PowerLawRate | None) -> PowerLaw:
    return PowerLaw(
        rate_units=_RATE_UNITS, k0=forward, Ea=ea, orders=orders, basis="mole_fraction", reverse=reverse
    )


def _field(body: Mapping[str, Any], rid: str, key: str) -> float:
    if key not in body:
        raise ReformerKineticError(f"kinetics.{rid} needs {key}")
    return float(body[key])


def _reaction_set(kinetics: Mapping[str, Any], p_atm: float) -> ReactionSet:
    """The Smith reactions at this pressure (spec equations 2-4)."""
    for rid in (*_REVERSIBLE, *_IRREVERSIBLE):
        if rid not in kinetics:
            raise ReformerKineticError(f"kinetics needs {rid}")
    fractions = {cid: 7.0 / 15.0 for cid in _LIGHTS}

    def reversible(rid: str, orders: dict[str, float], back: dict[str, float]) -> PowerLaw:
        body = kinetics[rid]
        k0, ea = _field(body, rid, "k0"), _field(body, rid, "Ea")
        a_k, b_k = _field(body, rid, "A_K"), _field(body, rid, "B_K")
        reverse = PowerLawRate(
            rate_units=_RATE_UNITS,
            k0=_fold_pressure(k0 * math.exp(-a_k), sum(back.values()), p_atm),
            Ea=ea - R * b_k,
            orders=back,
            basis="mole_fraction",
        )
        return _law(_fold_pressure(k0, sum(orders.values()), p_atm), ea, orders, reverse)

    def cracking(rid: str, base: str) -> PowerLaw:
        # p_i/P = y_i: the pressure cancels, so there is no fold.
        body = kinetics[rid]
        return _law(_field(body, rid, "k0"), _field(body, rid, "Ea"), {base: 1.0}, None)

    def reaction(rid: str, stoichiometry: dict[str, float], base: str, law: PowerLaw) -> Reaction:
        return Reaction(
            id=rid,
            stoichiometry=stoichiometry,
            base_component=base,
            provenance="Smith 1959 reaction scheme with n = 7; user constants",
            kinetics=law,
        )

    return ReactionSet(
        id="reformer_smith_r1",
        components=list(_SLATE),
        reactions=[
            reaction(
                "dehydro",
                {NAPHTHENE: -1.0, AROMATIC: 1.0, HYDROGEN: 3.0},
                NAPHTHENE,
                reversible("dehydro", {NAPHTHENE: 1.0}, {AROMATIC: 1.0, HYDROGEN: 3.0}),
            ),
            reaction(
                "n_to_p",
                {NAPHTHENE: -1.0, HYDROGEN: -1.0, PARAFFIN: 1.0},
                NAPHTHENE,
                reversible("n_to_p", {NAPHTHENE: 1.0, HYDROGEN: 1.0}, {PARAFFIN: 1.0}),
            ),
            reaction(
                "hc_n",
                {NAPHTHENE: -1.0, HYDROGEN: -7.0 / 3.0, **fractions},
                NAPHTHENE,
                cracking("hc_n", NAPHTHENE),
            ),
            reaction(
                "hc_p",
                {PARAFFIN: -1.0, HYDROGEN: -4.0 / 3.0, **fractions},
                PARAFFIN,
                cracking("hc_p", PARAFFIN),
            ),
        ],
    )


class CatalyticReformerR1:
    """Catalytic reformer on Smith's four reactions, level R1."""

    inlet_ports: tuple[str, ...] = ("naphtha_in",)
    outlet_ports: tuple[str, ...] = ("reformate_out", "h2_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["naphtha_in"]
        outside = sorted(set(feed.composition) - set(_SLATE))
        if outside:
            raise ReformerKineticError(
                f"feed species {outside} are outside the slate {list(_SLATE)}: a pseudo naphtha needs "
                "elemental characterisation (issue #222), use level R0"
            )
        beds = params.get("beds")
        if not isinstance(beds, list) or not beds:
            raise ReformerKineticError("beds must be a non-empty list")
        for i, bed in enumerate(beds):
            if float(bed.get("catalyst_mass_kg", 0.0)) <= 0.0:
                raise ReformerKineticError(f"beds[{i}].catalyst_mass_kg must be > 0")
            if float(bed.get("inlet_T_K", 0.0)) <= 0.0:
                raise ReformerKineticError(f"beds[{i}].inlet_T_K must be > 0")
            if bed.get("thermal", "adiabatic") not in ("adiabatic", "isothermal"):
                raise ReformerKineticError(f"beds[{i}].thermal must be 'adiabatic' or 'isothermal'")
        rho_b = params.get("bulk_density_kg_m3")
        if rho_b is None or float(rho_b) <= 0.0:
            raise ReformerKineticError("bulk_density_kg_m3 is required and must be > 0")
        bulk = float(rho_b)
        kinetics = params.get("kinetics")
        if kinetics == "smith1959":
            raise ReformerKineticError(
                "the smith1959 preset is not transcribed: Smith 1959 could not be read and its open "
                "reproduction leaves k2's units in doubt; pass the constants explicitly"
            )
        if not isinstance(kinetics, Mapping):
            raise ReformerKineticError("kinetics needs the explicit dehydro, n_to_p, hc_n and hc_p constants")
        rset = _reaction_set(kinetics, float(feed.P) / _PA_PER_ATM)

        info: dict[str, float] = {}
        state = feed
        n_now = feed.component_flows()
        duties = 0.0
        for k, bed in enumerate(beds):
            heated = thermo.flash_pt(dict(state.composition), float(bed["inlet_T_K"]), state.P, state.molar_flow)
            heat = (heated.enthalpy - state.enthalpy) * state.molar_flow
            info[f"heater_duty_b{k}_W"] = heat
            duties += heat
            thermal = bed.get("thermal", "adiabatic")
            profile = integrate_plug_flow(
                heated,
                rset,
                thermo,
                volume_m3=float(bed["catalyst_mass_kg"]) / bulk,
                energy=thermal,
                bulk_density_kg_m3=bulk,
            )
            xi = list(profile.extents[-1])
            n_now = apply_extents(heated.component_flows(), rset, xi)
            state, duty = thermal_outlet(heated, n_now, thermal, thermo)
            duties += duty
            info[f"bed_dT_b{k}_K"] = float(state.T) - float(heated.T)
            info[f"bed_T_out_b{k}_K"] = float(state.T)
            info[f"T_closure_gap_b{k}_K"] = float(state.T) - profile.T_K[-1]
            for reaction, value in zip(rset.reactions, xi, strict=True):
                info[f"extent_{reaction.id}_b{k}_mol_s"] = float(value)

        outlets: dict[str, StreamState] = {}
        for port, cids in (
            ("reformate_out", sorted(c for c, n in n_now.items() if n > 0.0 and c not in _TO_H2_OUT)),
            ("h2_out", sorted(c for c, n in n_now.items() if n > 0.0 and c in _TO_H2_OUT)),
        ):
            if not cids:
                raise ReformerKineticError(f"{port} would carry no species")
            total = math.fsum(n_now[c] for c in cids)
            outlets[port] = thermo.flash_pt({c: n_now[c] / total for c in cids}, state.T, state.P, total)

        duty_w = stream_enthalpy(outlets.values(), "formation") - stream_enthalpy([feed], "formation")
        mass = math.fsum(n * float(component_record(c)["mw"]) for c, n in feed.component_flows().items())
        made = n_now.get(HYDROGEN, 0.0) - feed.component_flows().get(HYDROGEN, 0.0)
        c6_plus = math.fsum(n_now.get(c, 0.0) for c in (NAPHTHENE, PARAFFIN, AROMATIC))
        info.update(
            split_enthalpy_W=duty_w - duties,
            h2_yield_wt_pct=100.0 * made * float(component_record(HYDROGEN)["mw"]) / mass,
            aromatics_out_mol_frac_C6plus=n_now.get(AROMATIC, 0.0) / c6_plus if c6_plus > 0.0 else 0.0,
        )
        return UnitResult(outlets=outlets, duty_W=duty_w, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Three adiabatic beds.  ALL constants are test inputs, NOT Smith's, not defaults."""
        total = 0.2 + 0.1 + 0.05 + 0.65
        feeds = {
            "naphtha_in": {
                "T": 700.0,
                "P": 2.0e6,
                "molar_flow": total,
                "composition": {NAPHTHENE: 0.2, PARAFFIN: 0.1, AROMATIC: 0.05, HYDROGEN: 0.65},
            }
        }
        params: dict[str, Any] = {
            "beds": [
                {"catalyst_mass_kg": 2.0, "inlet_T_K": 770.0},
                {"catalyst_mass_kg": 3.0, "inlet_T_K": 770.0},
                {"catalyst_mass_kg": 5.0, "inlet_T_K": 770.0},
            ],
            "bulk_density_kg_m3": 600.0,
            "kinetics": {
                "dehydro": {"k0": 2.0e3, "Ea": 8.0e4, "A_K": 46.15, "B_K": 25000.0},
                "n_to_p": {"k0": 2.0, "Ea": 6.0e4, "A_K": -7.0, "B_K": -4400.0},
                "hc_n": {"k0": 50.0, "Ea": 1.0e5},
                "hc_p": {"k0": 50.0, "Ea": 1.0e5},
            },
        }
        return feeds, params
