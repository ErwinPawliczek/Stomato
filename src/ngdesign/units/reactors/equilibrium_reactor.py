"""Equilibrium reactor: Keq-limited extents per reaction (spec U-F, R0).

Plugin kind "unit", name "equilibrium_reactor".

Method (spec): ports inlet -> outlet. Params ``reaction_set``, ``thermal``, and
the optional ``approach_dT`` (K) — K is evaluated at T + approach_dT while the
quotient uses the actual temperature, so a positive value stops short of
equilibrium. Extents solve the coupled system ln Q_j(ξ) = ln K_j; the quotient
is ideal-gas, Q = Π (y_i·P/P°)^ν_i, on the same standard state as the Gibbs
reactor (the V2 cross-check holds at 1e-6). ``info`` carries each reaction's
extent and ln K.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from scipy.optimize import fsolve

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Reaction, ReactionSet
from ngdesign.registry import register
from ngdesign.units._physics.kinetics import apply_extents, ln_keq
from ngdesign.units.reactors._shared import P_REF, reaction_set_param, thermal_outlet

#: Residual magnitude assigned to a reaction whose reactant side is depleted:
#: ln Q sits at +inf there, which no root-finder can bracket — the reaction
#: wants to proceed, so the residual points the same way.
_DEPLETED = -1.0e6


def _quotient_residual(
    reaction: Reaction,
    extent: float,
    n_in: Mapping[str, float],
    T: float,
    P: float,
    ln_k: float,
) -> float:
    """ln Q − ln K for one reaction at one extent; boundary-safe."""
    n: dict[str, float] = {cid: float(n) for cid, n in n_in.items()}
    for cid, nu in reaction.stoichiometry.items():
        n[cid] = n.get(cid, 0.0) + extent * nu
    if any(n[cid] <= 0.0 for cid, nu in reaction.stoichiometry.items() if nu < 0.0):
        return _DEPLETED
    total = math.fsum(n.values())
    ln_q = 0.0
    for cid, nu in reaction.stoichiometry.items():
        y = n[cid] / total
        ln_q += nu * math.log(max(y * P / P_REF, 1e-300))
    return ln_q - ln_k


def _extent_max(reaction: Reaction, n_in: Mapping[str, float]) -> float:
    """Largest extent before a reactant goes negative."""
    return min(float(n_in.get(cid, 0.0)) / abs(nu) for cid, nu in reaction.stoichiometry.items() if nu < 0.0)


def equilibrium_extents(
    rset: ReactionSet,
    n_in: Mapping[str, float],
    T: float,
    P: float,
    approach_dT: float,
) -> list[float]:
    """Extents solving ln Q_j = ln K_j for every reaction simultaneously."""
    ln_ks = [ln_keq(r, T + approach_dT) for r in rset.reactions]

    def system(x: list[float]) -> list[float]:
        return [
            _quotient_residual(reaction, max(xi, 0.0), n_in, T, P, ln_k)
            for reaction, xi, ln_k in zip(rset.reactions, x, ln_ks, strict=True)
        ]

    x0 = [
        0.5 * float(n_in.get(r.base_component, 0.0)) / abs(float(r.stoichiometry[r.base_component]))
        for r in rset.reactions
    ]
    sol, _info, ier, _msg = fsolve(system, x0, full_output=True, xtol=1e-12)
    if ier != 1 or any(not math.isfinite(v) for v in sol):
        raise ValueError(
            f"reaction set {rset.id!r}: equilibrium extent solve did not converge "
            f"(flag {ier}, residuals {system(list(sol))})"
        )
    clipped = [min(max(xi, 0.0), _extent_max(r, n_in)) for r, xi in zip(rset.reactions, sol, strict=True)]
    residuals = system(clipped)
    if any(abs(r) > 1e-6 and abs(r) < _DEPLETED for r in residuals):
        raise ValueError(
            f"reaction set {rset.id!r}: equilibrium residuals {residuals} exceed 1e-6 after clipping"
        )
    return clipped


@register("unit", "equilibrium_reactor")
class EquilibriumReactor:
    """Reactor relieving every reaction to its equilibrium limit (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        rset = reaction_set_param(params["reaction_set"])
        n_in = inlet.component_flows()
        extents = equilibrium_extents(rset, n_in, inlet.T, inlet.P, float(params.get("approach_dT", 0.0)))
        n_out = apply_extents(n_in, rset, extents)
        outlet, duty = thermal_outlet(inlet, n_out, params.get("thermal", "isothermal"), thermo)
        info: dict[str, float] = {
            f"extent_{reaction.id}": xi for reaction, xi in zip(rset.reactions, extents, strict=True)
        }
        for reaction in rset.reactions:
            info[f"lnK_{reaction.id}"] = ln_keq(reaction, inlet.T)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Water-gas shift, equimolar CO/H2O at 1100 K (the CMU case's T+100).

        Closed form: ln K(1100 K) = −0.00744 → X = sqrt(K)/(1+sqrt(K)) ≈
        0.49907, y_CO = (1−X)/2 and y_CO2 = X/2.
        """
        feed = {
            "T": 1100.0,
            "P": 1013250.0,
            "molar_flow": 2.0,
            "composition": {"CO": 0.5, "H2O": 0.5},
        }
        params = {
            "reaction_set": {
                "id": "wgs_case",
                "components": ["CO", "H2O", "CO2", "H2"],
                "reactions": [
                    {
                        "id": "wgsr",
                        "stoichiometry": {"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
                        "base_component": "CO",
                        "provenance": "water-gas shift, standard reference (e.g. SVA App. C)",
                        "equilibrium": {"form": "from_gibbs"},
                    }
                ],
            },
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params
