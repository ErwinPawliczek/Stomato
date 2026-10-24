"""Equilibrium reactor: Keq-limited extents per reaction (spec U-F, R0).

Method (spec): ports inlet -> outlet. Params ``reaction_set``, ``thermal`` and
the optional ``approach_K`` (K). The equilibrium constant is evaluated at

    T_eq = T_out − approach_K

so the extent stops short of the ideal limit; the sign convention is that the
equilibrium is evaluated at the temperature that gives *less* conversion than
ideal. For an endothermic reaction (e.g. steam-methane reforming) that is a
colder temperature, so a positive ``approach_K`` falls short; an exothermic
reaction (e.g. the water-gas shift, U-G's Claus row) falls short with a
negative ``approach_K`` — the same short-of-equilibrium semantics as Claus,
which evaluates K at ``T_out + approach`` on its hot side.

The outlet temperature itself depends on the thermal mode: ``isothermal``
(T_out = inlet T), ``{"T_out": K}`` (fixed), ``adiabatic`` (duty 0) and
``{"duty_W": q}`` solve T_out so the formation-enthalpy balance closes with the
extents re-equilibrated at every trial temperature (the solve is coupled, as
the Gibbs reactor's adiabatic mode is). Extents solve the coupled system
ln Q_j(ξ) = ln K_j(T_eq); the quotient is ideal-gas, Q = Π (y_i·P/P°)^ν_i, on
the same standard state as the Gibbs reactor (the V2 cross-check holds at
1e-6). ``info`` carries each reaction's extent and ln K at the T_eq actually
used. A solve that pushes a species negative or past its depletion limit is
refused, never clipped silently.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from scipy.optimize import brentq, fsolve

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Reaction, ReactionSet
from ngdesign.units._physics.kinetics import apply_extents, enthalpy_with_formation, ln_keq
from ngdesign.units.reactors._shared import _T_MAX, _T_MIN, P_REF, reaction_set_param, z_from

#: Residual magnitude assigned to a reaction whose reactant side is depleted:
#: ln Q sits at -inf there, which no root-finder can bracket — the reaction
#: wants to proceed, so the residual points the same way.
_DEPLETED = -1.0e6

#: Residuals between the 1e-6 tolerance and this floor mean the solver landed
#: near (but not on) a depletion boundary without converging: refused. Only
#: the exact boundary sentinel itself counts as "limited by depletion".
_DEPLETED_FLOOR = _DEPLETED / 2.0


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
    T_eq: float,
    P: float,
) -> list[float]:
    """Extents solving ln Q_j = ln K_j(T_eq) for every reaction simultaneously."""
    ln_ks = [ln_keq(r, T_eq) for r in rset.reactions]

    def system(x: list[float]) -> list[float]:
        return [
            _quotient_residual(reaction, max(xi, 0.0), n_in, T_eq, P, ln_k)
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
    moved = [
        reaction.id
        for reaction, xi, ci in zip(rset.reactions, sol, clipped, strict=True)
        if abs(ci - xi) > 1e-9
    ]
    if moved:
        raise ValueError(
            f"reaction set {rset.id!r}: equilibrium extent(s) for {moved} were clipped "
            "(the solve pushed a species negative or past its depletion limit); refusing"
        )
    residuals = system(clipped)
    bad = [
        reaction.id
        for reaction, residual in zip(rset.reactions, residuals, strict=True)
        if residual > 1e-6 or (abs(residual) > 1e-6 and residual > _DEPLETED_FLOOR)
    ]
    if bad:
        raise ValueError(
            f"reaction set {rset.id!r}: equilibrium residuals for {bad} exceed 1e-6 "
            f"({dict(zip([r.id for r in rset.reactions], residuals, strict=True))})"
        )
    return clipped


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
        approach = float(params.get("approach_K", 0.0))
        thermal = params.get("thermal", "isothermal")
        h_in_W = enthalpy_with_formation(inlet)

        def state_at(T_out: float) -> tuple[StreamState, list[float]]:
            """Outlet state + extents with equilibrium evaluated at T_out − approach_K."""
            extents = equilibrium_extents(rset, n_in, T_out - approach, inlet.P)
            n_out = apply_extents(n_in, rset, extents)
            outlet = thermo.flash_pt(z_from(n_out), T_out, inlet.P, math.fsum(n_out.values()))
            return outlet, extents

        if isinstance(thermal, Mapping) and set(thermal) == {"T_out"}:
            T_out = float(thermal["T_out"])
            outlet, extents = state_at(T_out)
            duty = enthalpy_with_formation(outlet) - h_in_W
        elif isinstance(thermal, str) and thermal == "isothermal":
            T_out = inlet.T
            outlet, extents = state_at(inlet.T)
            duty = enthalpy_with_formation(outlet) - h_in_W
        elif (
            isinstance(thermal, str)
            and thermal == "adiabatic"
            or (isinstance(thermal, Mapping) and set(thermal) == {"duty_W"})
        ):
            duty = 0.0 if isinstance(thermal, str) else float(thermal["duty_W"])
            target = h_in_W + duty

            def f(T: float) -> float:
                outlet, _ = state_at(T)
                return enthalpy_with_formation(outlet) - target

            lo, hi = max(_T_MIN, inlet.T - 400.0), inlet.T + 2000.0
            while f(lo) > 0.0 and lo > _T_MIN:
                lo = max(_T_MIN, lo - 500.0)
            if f(lo) > 0.0:
                raise ValueError(
                    "adiabatic heat balance is infeasible: even at 1 K the outlet enthalpy "
                    "exceeds the inlet enthalpy (the reaction heat exceeds all available sensible heat)"
                )
            while f(hi) < 0.0:
                if hi >= _T_MAX:
                    raise ValueError(
                        f"reactor outlet temperature exceeds {_T_MAX} K closing the heat balance"
                    )
                hi = min(_T_MAX, hi + 1000.0)
            T_out = float(brentq(f, lo, hi, xtol=1e-9, maxiter=200))
            outlet, extents = state_at(T_out)
        else:
            raise ValueError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
                '{"duty_W": W} or {"T_out": K}'
            )

        info: dict[str, float] = {
            f"extent_{reaction.id}": xi for reaction, xi in zip(rset.reactions, extents, strict=True)
        }
        for reaction in rset.reactions:
            info[f"lnK_{reaction.id}"] = ln_keq(reaction, T_out - approach)
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
