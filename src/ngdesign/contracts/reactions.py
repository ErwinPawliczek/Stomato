"""Reaction contracts: reactions, kinetics, equilibrium, reaction sets (spec U-R).

Flowsheet documents carry these models through ``Flowsheet.reactions``. All
refusals raise the typed errors of this module (which subclass ValueError);
construction through pydantic wraps them into ValidationError, matching the
rest of the contracts layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from ngdesign.data import component_record
from ngdesign.data.formation import atomic_composition

from .common import Model


class ReactionError(ValueError):
    """Base class for reaction contract refusals."""


class UnknownComponentError(ReactionError):
    """A reaction or set references a component outside the declared slate."""


class ZeroStoichiometryError(ReactionError):
    """A stoichiometry entry is zero."""


class ElementBalanceError(ReactionError):
    """Element (or lumped mass) balance is violated."""


class DuplicateReactionIdError(ReactionError):
    """Two reactions in one set share an id."""


#: Rate basis: mole-fraction driving force, or concentration c_i = y_i·P/(R·T).
RateBasis = Literal["mole_fraction", "concentration"]


class Arrhenius(Model):
    """Arrhenius factor k0·exp(−Ea/(R·T)) with Ea in J/mol."""

    k0: float
    Ea: float


class DrivingForceTerm(Model):
    """One additive term of an LHHW numerator/denominator block."""

    arrhenius: Arrhenius
    orders: dict[str, float] = {}


class PowerLaw(Model):
    """Power-law rate expression.

    ``reverse`` carries the explicit reverse expression; without it a reaction
    with an equilibrium model is equilibrium-limited, and without either the
    expression is irreversible.
    """

    rate_units: str  # documentation only, e.g. "mol/(m3·s)"
    k0: float
    Ea: float
    orders: dict[str, float] = {}
    basis: RateBasis = "mole_fraction"
    reverse: PowerLaw | None = None


class LHHW(Model):
    """Langmuir-Hinshelwood-Hougen-Watson rate expression."""

    rate_units: str
    basis: RateBasis = "mole_fraction"
    driving_force: list[DrivingForceTerm]
    adsorption: list[DrivingForceTerm] = []
    adsorption_exponent: float = 1.0


class Equilibrium(Model):
    """Equilibrium model of one reaction: Gibbs-driven or a ln K polynomial."""

    form: Literal["from_gibbs", "polynomial"]
    # ln K = Σ_a c_a·T^a over ``polynomial`` items; keys are exponent powers.
    polynomial: dict[float, float] = {}
    # Closed [Tmin, Tmax] window the polynomial fit is valid in, K.
    t_window: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _polynomial_window(self) -> Equilibrium:
        if self.form == "polynomial":
            if not self.polynomial:
                raise ReactionError("equilibrium polynomial form requires polynomial coefficients")
            if self.t_window is None:
                raise ReactionError("equilibrium polynomial form requires a t_window [Tmin, Tmax]")
        return self


class Reaction(Model):
    """One stoichiometric reaction with optional kinetics and equilibrium model.

    ``base_component`` is the component the extent of reaction is normalized
    on; it must appear with ν < 0. Pseudo (lumped) components can only take
    part in reactions explicitly marked ``lumped``, which switches validation
    from element balances to a molecular-weight balance (pseudos carry no
    formula). ``provenance`` is mandatory: every reaction names where its
    stoichiometry and data come from.
    """

    id: str
    stoichiometry: dict[str, float]
    base_component: str
    provenance: str
    kinetics: PowerLaw | LHHW | None = None
    equilibrium: Equilibrium | None = None
    lumped: bool = False

    @model_validator(mode="after")
    def _validate(self) -> Reaction:
        if not self.id.strip():
            raise ReactionError("reaction id is required and non-empty")
        if not self.provenance.strip():
            raise ReactionError(f"reaction {self.id!r}: provenance is required and non-empty")
        zero = sorted(cid for cid, nu in self.stoichiometry.items() if nu == 0.0)
        if zero:
            raise ZeroStoichiometryError(f"reaction {self.id!r}: ν = 0 entries for {zero}")
        nu_base = self.stoichiometry.get(self.base_component)
        if nu_base is None:
            raise ReactionError(
                f"reaction {self.id!r}: base_component {self.base_component!r} is not in the stoichiometry"
            )
        if nu_base >= 0.0:
            raise ReactionError(
                f"reaction {self.id!r}: base_component {self.base_component!r} must appear with ν < 0"
            )
        for cid in self.stoichiometry:
            record = component_record(cid)
            if record["kind"] == "pseudo" and not self.lumped:
                raise ReactionError(f"reaction {self.id!r}: pseudo component {cid!r} requires lump=True")
        if not self.lumped:
            self._check_element_balance()
        return self

    def _check_element_balance(self) -> None:
        atoms = {cid: atomic_composition(cid) for cid in self.stoichiometry}
        elements: set[str] = set()
        for per_component in atoms.values():
            elements |= set(per_component)
        for element in sorted(elements):
            net = 0.0
            scale = 0.0
            for cid, nu in self.stoichiometry.items():
                term = nu * atoms[cid].get(element, 0)
                net += term
                scale = max(scale, abs(term))
            if scale == 0.0:
                continue
            relative = net / scale
            if abs(relative) > 1e-6:
                raise ElementBalanceError(
                    f"reaction {self.id!r}: element {element} balance violated by {relative:.3e} relative"
                )


class ReactionSet(Model):
    """A flowsheet-owned set of reactions over its own component slate.

    The slate is self-describing so a saved project carries everything needed
    to replay it; the flowsheet slate may be wider. Lumped reactions are
    validated on a molecular-weight balance instead of element counts.
    """

    id: str
    reactions: list[Reaction]
    components: list[str]

    @model_validator(mode="after")
    def _validate(self) -> ReactionSet:
        if not self.id.strip():
            raise ReactionError("reaction set id is required and non-empty")
        ids = [r.id for r in self.reactions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicates:
            raise DuplicateReactionIdError(f"reaction set {self.id!r}: duplicate reaction ids {duplicates}")
        slate = set(self.components)
        for reaction in self.reactions:
            outside = set(reaction.stoichiometry) - slate
            if outside:
                raise UnknownComponentError(
                    f"reaction set {self.id!r}: reaction {reaction.id!r} uses component "
                    f"{sorted(outside)[0]!r} outside the component slate"
                )
            if reaction.lumped:
                self._check_mass_balance(reaction)
        return self

    def _check_mass_balance(self, reaction: Reaction) -> None:
        net = 0.0
        scale = 0.0
        for cid, nu in reaction.stoichiometry.items():
            mw = float(component_record(cid)["mw"])
            net += nu * mw
            scale = max(scale, abs(nu * mw))
        if scale == 0.0:
            return
        relative = net / scale
        if abs(relative) > 0.02:
            raise ElementBalanceError(
                f"reaction set {self.id!r}: lumped reaction {reaction.id!r} mass balance "
                f"violated by {relative:.3e} relative"
            )


PowerLaw.model_rebuild()
