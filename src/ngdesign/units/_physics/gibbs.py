"""Gibbs minimisation over a species set (spec U-F, gibbs-reactor core).

Standard chemical potentials assemble exactly on the
:func:`ngdesign.units._physics.kinetics.ln_keq` path (NIST-JANAF style,
element reference, ideal-gas standard state at :data:`P_REF`) — the same
assembly that produces equilibrium constants, which is why the Gibbs and
equilibrium reactors cross-check to 1e-6 (spec U-F V2). Minimisation is by
Newton's method (``scipy.optimize.fsolve``) on the element-potential
stationarity conditions — equal chemical potentials of each element across its
species — with element-budget equality constraints; inert
species carry fixed amounts and never enter the objective.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from scipy.optimize import fsolve

from ngdesign.data.formation import (
    atomic_composition,
    formation_enthalpy_298,
    integral_cp,
    standard_entropy_298,
)
from ngdesign.units._physics.kinetics import R

#: JANAF ideal-gas standard-state pressure for chemical potentials, Pa.
P_REF = 1.0e5

#: Bounds floor for species amounts, mol/s: keeps ln n finite in the objective.
_N_FLOOR = 1e-12


class GibbsError(ValueError):
    """Raised when a Gibbs minimisation is ill-posed or fails to converge."""


def standard_potential(cid: str, T: float) -> float:
    """μ°(T) of one species on the element reference, J/mol (the ln_keq path)."""
    return (
        formation_enthalpy_298(cid)
        - T * standard_entropy_298(cid)
        + integral_cp(cid, T, over_t=False)
        - T * integral_cp(cid, T, over_t=True)
    )


def thermoneutral_voltage() -> float:
    """|ΔfH°(298, H2O gas)| / (2F): the LHV (water-vapour) basis, V.

    The databank's water is gas-phase, so this is 241826/(2·96485.33212) ≈
    1.253 V; the liquid-water (HHV) value including vaporisation enthalpy is
    1.481 V and is deliberately not used.
    """
    return abs(formation_enthalpy_298("H2O")) / (2.0 * 96485.33212)


def element_budgets(
    species: Sequence[str], inerts: Sequence[str], n_in: Mapping[str, float]
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Element budget system A·n = b for the species amounts, mol/s of atoms.

    ``b`` is the feed's atom flow per element (inert atoms included — they
    cannot react, so their atoms must appear in the species set or the system
    is infeasible). Rows are in sorted-element order. Refuses when an element
    present in the feed (reactive or inert) is carried by no species.
    """
    rows: dict[str, dict[str, int]] = {cid: atomic_composition(cid) for cid in species}
    elements = sorted(set().union(*rows.values())) if rows else []
    b = np.zeros(len(elements))
    for cid, n in n_in.items():
        atoms = atomic_composition(cid)
        for el, count in atoms.items():
            if el not in elements:
                raise GibbsError(
                    f"element {el!r} (from feed component {cid!r}) is carried by no "
                    f"species in the set {sorted(species)}"
                )
            b[elements.index(el)] += count * float(n)
    A = np.array(
        [[float(rows[cid].get(el, 0)) for cid in species] for el in elements],
        dtype=float,
    )
    return elements, A, b


def gibbs_minimum(
    species: Sequence[str],
    inerts: Sequence[str],
    n_in: Mapping[str, float],
    T: float,
    P: float,
) -> dict[str, float]:
    """Equilibrium mole amounts by Gibbs minimisation, mol/s.

    Minimises G/RT = Σ_i n_i·(μ°_i/RT + ln(y_i·P/P°)) subject to the element
    budgets. Solved at the stationarity conditions (the element-potential
    method): μ°_i/RT + ln(y_i·P/P°) + Σ_j λ_j·a_ij = 0 plus A·n = b — a square
    system in (ln n_i, λ_j) whose residuals reach machine precision, where
    SLSQP's scalar tolerance stalls orders of magnitude short of the 1e-6
    equilibrium cross-check. Inerts contribute fixed amounts to the mole
    fractions but no degrees of freedom. Refuses on solver failure or a budget
    residual above 1e-8 relative.
    """
    if not species:
        raise GibbsError("gibbs minimisation needs a non-empty species set")
    elements, A, b = element_budgets(species, inerts, n_in)
    n_inert = math.fsum(float(n_in.get(cid, 0.0)) for cid in inerts)
    n_feed = math.fsum(float(n) for n in n_in.values())
    mu0 = np.array([standard_potential(cid, T) for cid in species]) / (R * T)
    ln_ppref = math.log(P / P_REF)
    n_s = len(species)
    n_e = len(elements)

    def residual(x: np.ndarray) -> np.ndarray:
        """Stationarity (species) + budget (element) residuals, in (ln n, λ)."""
        u, lam = x[:n_s], x[n_s:]
        n = np.exp(u)
        total = math.fsum(n) + n_inert
        return np.concatenate(
            [
                mu0 + np.log(n / total) + ln_ppref + A.T @ lam,
                A @ n - b,
            ]
        )

    x0 = np.concatenate([np.full(n_s, math.log(max(n_feed, 1.0) / n_s)), np.zeros(n_e)])
    sol, _info, ier, _msg = fsolve(residual, x0, full_output=True, xtol=1e-13)
    if ier != 1 or not np.all(np.isfinite(sol)):
        raise GibbsError(
            f"gibbs minimisation did not converge (flag {ier}, "
            f"max residual {np.abs(residual(sol)).max():.3e})"
        )
    n = np.exp(sol[:n_s])
    budget_residual = float(np.sum(np.abs(A @ n - b)))
    if budget_residual > 1e-8 * max(1.0, float(np.abs(b).sum())):
        raise GibbsError(f"gibbs minimisation violated the element budgets by {budget_residual:.3e}")
    return {cid: float(ni) for cid, ni in zip(species, n, strict=True)}
