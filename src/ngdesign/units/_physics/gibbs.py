"""Gibbs minimisation for the reactor units (spec U-F, C-02).

Standard chemical potentials are those of the species models in the cited database
(element reference, ideal-gas standard state at :data:`P_REF`), the same data
:func:`ngdesign.units._physics.kinetics.ln_keq` assembles, so the Gibbs and
equilibrium reactors cross-check to 1e-6 (spec U-F V2). The minimisation itself is
the one solver in :mod:`ngdesign.units._physics.gibbs_phases`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ngdesign.data.formation import MissingFormationData, formation_enthalpy_298, gas_model
from ngdesign.units._physics.gibbs_phases import P_STANDARD, EquilibriumError, gibbs_equilibrium

#: JANAF ideal-gas standard-state pressure for chemical potentials, Pa.
P_REF = P_STANDARD


class GibbsError(ValueError):
    """Raised when a Gibbs minimisation is ill-posed or fails to converge."""


def standard_potential(cid: str, T: float) -> float:
    """μ°(T) of one species on the element reference, J/mol."""
    return gas_model(cid).g(T)


def thermoneutral_voltage() -> float:
    """|ΔfH°(298, H2O gas)| / (2F): the LHV (water-vapour) basis, V.

    The databank's water is gas-phase, so this is 241826/(2·96485.33212) ≈
    1.253 V; the liquid-water (HHV) value including vaporisation enthalpy is
    1.481 V and is deliberately not used.
    """
    return abs(formation_enthalpy_298("H2O")) / (2.0 * 96485.33212)


def gibbs_minimum(
    species: Sequence[str],
    inerts: Sequence[str],
    n_in: Mapping[str, float],
    T: float,
    P: float,
) -> dict[str, float]:
    """Equilibrium amounts of ``species`` by Gibbs minimisation, mol/s.

    Minimises G/RT = Σ_i n_i·(μ°_i/RT + ln(y_i·P/P°)) over ideal-gas species subject to
    the feed's element budgets. Inerts dilute the mixture at their fixed amounts and
    contribute no atoms and no degrees of freedom. Refuses (:class:`GibbsError`) on an
    empty species set, a feed element no species carries, or non-convergence.
    """
    if not species:
        raise GibbsError("gibbs minimisation needs a non-empty species set")
    reactive = {cid: float(n) for cid, n in n_in.items() if cid not in inerts}
    spectators = {cid: float(n_in.get(cid, 0.0)) for cid in inerts}
    try:
        for cid in species:
            gas_model(cid)
        result = gibbs_equilibrium(reactive, list(species), T, P, inerts=spectators)
    except (EquilibriumError, MissingFormationData) as exc:
        raise GibbsError(str(exc)) from exc
    return {cid: result.gas.get(cid, 0.0) for cid in species}
