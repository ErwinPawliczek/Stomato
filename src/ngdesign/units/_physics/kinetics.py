"""Reaction physics over the data layer (spec U-R).

Rates, extents of reaction, equilibrium constants and heats of reaction. All
SI: J, mol, K, Pa, s. Ideal-gas standard state; equilibrium constants ride the
databank formation properties of ``ngdesign.data.formation``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ngdesign.contracts.reactions import (
    LHHW,
    Arrhenius,
    PowerLaw,
    PowerLawRate,
    Reaction,
    ReactionSet,
)
from ngdesign.data import component_record
from ngdesign.data.formation import (
    formation_enthalpy,
    formation_enthalpy_298,
    integral_cp,
    standard_entropy_298,
)

#: CODATA 2018 molar gas constant, J/(mol K).
R = 8.31446261815324

if TYPE_CHECKING:
    from ngdesign.contracts.stream import StreamState


class KineticsError(ValueError):
    """Raised when kinetics, extents or equilibrium requests are ill-posed."""


class ReactionExtentError(KineticsError):
    """Raised when applying extents would drive components negative."""


def _arrhenius_k(kinetics: Arrhenius, T: float) -> float:
    return float(kinetics.k0) * math.exp(-float(kinetics.Ea) / (R * T))


def _basis_amounts(basis: str, T: float, P: float, z: Mapping[str, float]) -> dict[str, float]:
    """Driving-force amounts per component on the expression's basis."""
    if basis == "mole_fraction":
        return {cid: float(y) for cid, y in z.items()}
    # concentration: c_i = y_i·P/(R·T), mol/m3
    return {cid: float(y) * P / (R * T) for cid, y in z.items()}


def _power_law_rate(kinetics: PowerLawRate, T: float, P: float, z: Mapping[str, float]) -> float:
    amounts = _basis_amounts(kinetics.basis, T, P, z)
    value = _arrhenius_k(Arrhenius(k0=kinetics.k0, Ea=kinetics.Ea), T)
    for cid, order in kinetics.orders.items():
        if cid not in amounts:
            raise KineticsError(f"kinetics order references component {cid!r} outside the mixture")
        value *= amounts[cid] ** order
    return value


def _arrhenius_power(
    term: Arrhenius, orders: Mapping[str, float], basis: str, T: float, P: float, z: Mapping[str, float]
) -> float:
    amounts = _basis_amounts(basis, T, P, z)
    value = _arrhenius_k(term, T)
    for cid, order in orders.items():
        if cid not in amounts:
            raise KineticsError(f"kinetics order references component {cid!r} outside the mixture")
        value *= amounts[cid] ** order
    return value


#: Standard-state pressure of the formation data (``ngdesign.data.formation``), Pa.
P_STANDARD = 1.0e5


def _equilibrium_limited(
    reaction: Reaction, forward: float, T: float, P: float, z: Mapping[str, float]
) -> float:
    """forward * (1 - Q/K), with Q the ideal-gas activity quotient prod (z_i P / P°)^nu_i.

    The rate vanishes at equilibrium (Q = K) and changes sign beyond it. A zero
    forward rate stays zero (the form carries no separate reverse rate). A
    reactant absent while the forward rate is nonzero makes Q infinite and is
    refused: give that reaction an explicit ``reverse`` expression instead.
    """
    if forward == 0.0:
        return 0.0
    ln_q = 0.0
    for cid, nu in reaction.stoichiometry.items():
        y = z.get(cid, 0.0)
        if y <= 0.0:
            if nu < 0.0:
                raise KineticsError(
                    f"reaction {reaction.id!r}: reactant {cid!r} is absent but the forward rate is "
                    "nonzero, so the activity quotient is infinite; give an explicit reverse expression"
                )
            return forward
        ln_q += nu * math.log(y * P / P_STANDARD)
    return forward * (1.0 - math.exp(ln_q - ln_keq(reaction, T)))


def rate(reaction: Reaction, T: float, P: float, z: Mapping[str, float]) -> float:
    """Rate of one reaction on its base-component extent basis.

    No kinetics model gives 0.0. Power law: explicit reverse expression wins,
    then equilibrium limitation forward * (1 - Q/K) when the reaction carries an
    equilibrium model, otherwise the bare forward expression.
    """
    kinetics = reaction.kinetics
    if kinetics is None:
        return 0.0
    if isinstance(kinetics, PowerLaw):
        forward = _power_law_rate(kinetics, T, P, z)
        if kinetics.reverse is not None:
            return forward - _power_law_rate(kinetics.reverse, T, P, z)
        if reaction.equilibrium is not None:
            return _equilibrium_limited(reaction, forward, T, P, z)
        return forward
    if isinstance(kinetics, LHHW):
        numerator = float(
            sum(
                _arrhenius_power(term.arrhenius, term.orders, kinetics.basis, T, P, z)
                for term in kinetics.driving_force
            )
        )
        denominator = float(
            float(
                sum(
                    _arrhenius_power(term.arrhenius, term.orders, kinetics.basis, T, P, z)
                    for term in kinetics.adsorption
                )
            )
            ** float(kinetics.adsorption_exponent)
        )
        return numerator / denominator
    raise KineticsError(f"reaction {reaction.id!r}: unsupported kinetics form {type(kinetics).__name__}")


def ln_keq(reaction: Reaction, T: float) -> float:
    """Natural log of the equilibrium constant of one reaction at T.

    ``from_gibbs`` assembles ln K = −ΔG°(T)/(R·T) on the reaction path,
    NIST-JANAF style: ΔrG°(T) = ΔrH°(298) − T·ΔrS°(298) + ∫ΔrCp dT
    − T·∫ΔrCp/T dT, with ΔrCp(T) = Σν·Cp(T) over all stoichiometric species.
    No per-species ΔfG(T) is formed: the per-species element-reference
    bookkeeping drops the sensible-heat terms of elemental species
    (ΔfG(element, T) ≡ 0), which mis-states any reaction in which an element
    appears with nonzero stoichiometric coefficient (H2 in the water-gas
    shift). Elemental species contribute exactly zero formation enthalpy,
    and their standard entropies enter through ΔrS°(298).
    ``polynomial`` evaluates its T-power series and refuses temperatures
    outside the declared window.
    """
    equilibrium = reaction.equilibrium
    if equilibrium is None:
        raise KineticsError(f"reaction {reaction.id!r}: no equilibrium model")
    if equilibrium.form == "polynomial":
        window = equilibrium.t_window
        if window is None or not window[0] <= T <= window[1]:
            window_repr = "none" if window is None else f"[{window[0]}, {window[1]}] K"
            raise KineticsError(
                f"reaction {reaction.id!r}: equilibrium polynomial evaluated at {T} K "
                f"outside its validity window {window_repr}"
            )
        return float(sum(coeff * T**power for power, coeff in equilibrium.polynomial.items()))
    delta_h_298 = float(sum(nu * formation_enthalpy_298(cid) for cid, nu in reaction.stoichiometry.items()))
    delta_s_298 = float(sum(nu * standard_entropy_298(cid) for cid, nu in reaction.stoichiometry.items()))
    delta_cp = float(
        sum(nu * integral_cp(cid, T, over_t=False) for cid, nu in reaction.stoichiometry.items())
    )
    delta_cp_over_t = float(
        sum(nu * integral_cp(cid, T, over_t=True) for cid, nu in reaction.stoichiometry.items())
    )
    delta_g = delta_h_298 - T * delta_s_298 + delta_cp - T * delta_cp_over_t
    return -delta_g / (R * T)


def equilibrium_constant(reaction: Reaction, T: float) -> float:
    """K = exp(ln K) of one reaction at T."""
    return math.exp(ln_keq(reaction, T))


def heat_of_reaction(reaction: Reaction, T: float) -> float:
    """ΔH°(T) per extent of reaction, J/mol, from the databank formation enthalpies.

    Elemental species contribute exactly zero, so the sum is the reaction
    enthalpy on the element reference.
    """
    return float(sum(nu * formation_enthalpy(cid, T) for cid, nu in reaction.stoichiometry.items()))


def enthalpy_with_formation(state: StreamState) -> float:
    """Stream enthalpy lifted to an element reference, J/s: molar flow times the
    package enthalpy (sensible + residual) plus each species' formation enthalpy.

    The package enthalpy reference sits near zero for elemental species at
    298.15 K, so a reaction's product−reactant difference reproduces the
    databank heat of reaction; this is the stream-side quantity reaction units
    must balance against their heat duty.
    """
    lift = float(sum(y * formation_enthalpy(cid, state.T) for cid, y in state.composition.items()))
    return float(state.molar_flow) * (float(state.enthalpy) + lift)


def stoich_matrix(rset: ReactionSet, slate: Sequence[str]) -> list[list[float]]:
    """ν[j][i]: stoichiometric coefficient of reaction j on component slate[i].

    Refuses (naming the component) when a reaction reaches outside the slate.
    """
    known = set(slate)
    for reaction in rset.reactions:
        outside = set(reaction.stoichiometry) - known
        if outside:
            raise KineticsError(
                f"reaction set {rset.id!r}: reaction {reaction.id!r} uses component "
                f"{sorted(outside)[0]!r} outside the slate"
            )
    return [[float(r.stoichiometry.get(cid, 0.0)) for cid in slate] for r in rset.reactions]


def apply_extents(n_in: Mapping[str, float], rset: ReactionSet, extents: Sequence[float]) -> dict[str, float]:
    """Advance mole amounts ``n_in`` through one set's reactions by ``extents``.

    n_out[cid] = n_in[cid] + Σ_j ν_j,cid·ξ_j. Components absent from ``n_in``
    start at zero. Refuses (naming the components) when the result would go
    negative.
    """
    if len(extents) != len(rset.reactions):
        raise KineticsError(
            f"reaction set {rset.id!r}: got {len(extents)} extents for {len(rset.reactions)} reactions"
        )
    n_out = {cid: float(n) for cid, n in n_in.items()}
    for reaction, xi in zip(rset.reactions, extents, strict=True):
        for cid, nu in reaction.stoichiometry.items():
            n_out[cid] = n_out.get(cid, 0.0) + xi * nu
    negative = sorted(cid for cid, n in n_out.items() if n < 0.0)
    if negative:
        raise ReactionExtentError(f"reaction set {rset.id!r}: extents drive components {negative} negative")
    return n_out


def yield_shift(
    n_in: Mapping[str, float],
    feed_cids: Sequence[str],
    yields_mass: Sequence[float],
    products: Sequence[str],
) -> dict[str, float]:
    """Lumped mass-basis yield shift (spec U-F step 1, yield reactor core).

    The declared feed components are consumed; each product is formed from the
    consumed mass at its mass yield — kg of product per kg of consumed feed,
    with ``yields_mass[i]`` belonging to ``products[i]`` and ``Σ = 1``. Outlet
    moles follow from each product's molar mass (``component_record``,
    pseudo-components included). Components outside the declared feed pass
    through untouched; a product may also name a feed component (unconverted
    recycle lumps): the feed amount is zeroed first, then the product amount
    is added.

    Refuses (KineticsError, naming the offender): ``products`` and
    ``yields_mass`` of different lengths, a negative yield, yields not
    summing to 1 within 1e-9, duplicate product ids, and a declared feed
    component absent from ``n_in``.
    """
    if len(yields_mass) != len(products):
        raise KineticsError(f"yield shift: {len(products)} product ids for {len(yields_mass)} mass yields")
    seen: set[str] = set()
    for cid in products:
        if cid in seen:
            raise KineticsError(f"yield shift: duplicate product {cid!r}")
        seen.add(cid)
    total_yield = math.fsum(yields_mass)
    if any(y < 0.0 for y in yields_mass):
        negative = sorted(cid for cid, y in zip(products, yields_mass, strict=True) if y < 0.0)
        raise KineticsError(f"yield shift: negative mass yield for {negative}")
    nan = [cid for cid, y in zip(products, yields_mass, strict=True) if not math.isfinite(y)]
    if nan:
        raise KineticsError(f"yield shift: mass yield for {nan} is not finite")
    if abs(total_yield - 1.0) > 1e-9:
        raise KineticsError(f"yield shift: mass yields sum to {total_yield!r}, not 1 within 1e-9")

    n_out = {cid: float(n) for cid, n in n_in.items()}
    consumed_mass = 0.0
    for cid in feed_cids:
        if cid not in n_out:
            raise KineticsError(f"yield shift: declared feed component {cid!r} is not in the mixture")
        consumed_mass += float(n_out[cid]) * float(component_record(cid)["mw"])
        n_out[cid] = 0.0
    for cid, y in zip(products, yields_mass, strict=True):
        n_out[cid] = n_out.get(cid, 0.0) + y * consumed_mass / float(component_record(cid)["mw"])
    return n_out
