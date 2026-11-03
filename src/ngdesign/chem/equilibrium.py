"""Chemical equilibrium: the Gibbs solver plus equilibrium of stated reactions.

:func:`gibbs_equilibrium` and :func:`adiabatic_equilibrium` live in
``ngdesign.units._physics.gibbs_phases`` so flowsheet units can use them.
:func:`reaction_equilibrium` is here because it needs reaction thermochemistry: it
lets only the listed reactions run, where the Gibbs solver lets every candidate form.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linprog

from ngdesign.chem.stoichiometry import Equation, balance
from ngdesign.chem.thermochem import P_STANDARD, ReactionThermo, reaction_thermo
from ngdesign.units._physics.gibbs_phases import (
    _MAX_ITERATIONS,
    EquilibriumError,
    EquilibriumResult,
    adiabatic_equilibrium,
    gibbs_equilibrium,
)
from ngdesign.uom.quantity import si_arguments


@dataclass(frozen=True)
class ExtentEquilibrium:
    """Equilibrium of a stated reaction list: only these reactions may happen."""

    T: float
    P: float
    extents: dict[str, float]  # mol of reaction, by equation string
    amounts: dict[str, float]  # mol
    constants: dict[str, ReactionThermo]


@si_arguments(T="temperature", P="pressure")
def reaction_equilibrium(
    reactions: Sequence[str | Equation],
    feed: Mapping[str, float],
    T: float,
    P: float = 101325.0,
) -> ExtentEquilibrium:
    """Equilibrium extents of given gas-phase reactions, keeping everything else frozen.

    Unlike :func:`gibbs_equilibrium`, which lets every listed species form, this
    respects kinetic reality: a species reachable only through a reaction not on the
    list stays at its feed amount. Solves Σ_i ν_ij ln a_i = ln K_j(T) for each j by
    damped Newton in the extents, starting from an interior point.
    Species in ``feed`` that no reaction touches count as inerts.
    """
    equations = [balance(r) if isinstance(r, str) else r for r in reactions]
    if not equations:
        raise EquilibriumError("no reactions given")
    phases: dict[str, str] = {}
    keys: list[str] = list(feed)
    for eq in equations:
        for term in eq.terms:
            if term.key not in keys:
                keys.append(term.key)
            phases[term.key] = term.phase or "gas"
    condensed = sorted(k for k, phase in phases.items() if phase not in ("gas", None))
    if condensed:
        raise EquilibriumError(f"reaction_equilibrium is gas-phase; use gibbs_equilibrium for {condensed}")
    thermo = [reaction_thermo(eq, T, phases={t.key: "gas" for t in eq.terms}) for eq in equations]
    ln_k = np.array([t.lnK for t in thermo])
    nu = np.array([[eq.nu.get(key, 0.0) for key in keys] for eq in equations])
    n0 = np.array([float(feed.get(key, 0.0)) for key in keys])
    if (n0 < 0.0).any():
        raise EquilibriumError("negative feed amount")
    ln_p = math.log(P / P_STANDARD)
    # products absent from the feed sit on a singular log, so start from an interior point
    xi = _interior_start(nu, n0)

    def residual(extent: NDArray[np.float64]) -> NDArray[np.float64]:
        n = n0 + nu.T @ extent
        y = n / n.sum()
        return np.asarray(nu @ (np.log(y) + ln_p) - ln_k, dtype=float)

    for _ in range(_MAX_ITERATIONS):
        f = residual(xi)
        if float(np.abs(f).max()) < 1e-10:
            break
        n = n0 + nu.T @ xi
        total = float(n.sum())
        jac = nu @ np.diag(1.0 / n) @ nu.T - np.outer(nu.sum(axis=1), nu.sum(axis=1)) / total
        step = np.linalg.solve(jac, -f)
        lam = 1.0
        for _ in range(60):
            trial = n0 + nu.T @ (xi + lam * step)
            if (trial > 0.0).all() and np.abs(residual(xi + lam * step)).max() < np.abs(f).max() * (
                1 - 1e-4 * lam
            ):
                break
            lam *= 0.5
        xi = xi + lam * step
    else:
        raise EquilibriumError("reaction equilibrium Newton did not converge")
    amounts = n0 + nu.T @ xi
    return ExtentEquilibrium(
        T,
        P,
        {str(eq): float(x) for eq, x in zip(equations, xi, strict=True)},
        {key: float(n) for key, n in zip(keys, amounts, strict=True)},
        {str(eq): t for eq, t in zip(equations, thermo, strict=True)},
    )


def _interior_start(nu: NDArray[np.float64], n0: NDArray[np.float64]) -> NDArray[np.float64]:
    """Extents that leave every species present, by the LP max t: n0 + νᵀξ ≥ t."""
    n_reactions, n_species = nu.shape
    cost = np.zeros(n_reactions + 1)
    cost[-1] = -1.0
    constraint = np.hstack([-nu.T, np.ones((n_species, 1))])
    solved = linprog(
        cost, A_ub=constraint, b_ub=n0, bounds=[(None, None)] * n_reactions + [(None, float(n0.sum()))]
    )
    if not solved.success or float(solved.x[-1]) <= 0.0:
        raise EquilibriumError(
            "no composition has every species present: the feed lacks what the reactions consume"
        )
    return np.asarray(solved.x[:-1], dtype=float)


__all__ = [
    "EquilibriumError",
    "EquilibriumResult",
    "ExtentEquilibrium",
    "adiabatic_equilibrium",
    "gibbs_equilibrium",
    "reaction_equilibrium",
]
