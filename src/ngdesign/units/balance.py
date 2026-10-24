"""Balance bases for unit results: the one owner of what "closes" means (spec U-01).

A catalogue row declares ``balance: molar`` (no reaction: every component's
molar flow is conserved) or ``balance: mass_elements`` (reactive: total mass
and every element's atom flow are conserved; pseudo-components, which have no
formula, carry mass only).

Energy on ``mass_elements`` rows closes on the formation-enthalpy basis, so a
heat of reaction shows in the stream enthalpies rather than the duty. When a
stream carries a species without formation data (a petroleum pseudo-component)
that basis does not exist; the unit must then say so by setting
:data:`SENSIBLE_ONLY_FLAG` in its info, and energy closes on the package
(sensible) enthalpy instead. A reactive unit that leaves the flag out while a
species lacks formation data is a finding, never a silent fallback.

Both ``scripts/validate_units.py`` (V0) and ``tests/property/test_unit_balances.py``
call these functions, so the two checks cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

from ngdesign.contracts.stream import StreamState
from ngdesign.data import component_record
from ngdesign.data.formation import MissingFormationData, atomic_composition, formation_enthalpy
from ngdesign.units._physics.kinetics import enthalpy_with_formation

#: Info key a reactive unit sets (to a nonzero value) when it reports its duty on
#: the package-enthalpy basis because a species has no formation enthalpy.
SENSIBLE_ONLY_FLAG = "heat_of_reaction_basis_sensible_only"

EnergyBasis = Literal["sensible", "formation", "sensible_declared"]


class BalanceBasisError(ValueError):
    """The declared balance basis cannot be evaluated on these streams."""


def mass_and_atoms(states: Iterable[StreamState]) -> tuple[float, dict[str, float]]:
    """Total mass flow (g/s) and per-element atom flows (mol/s) of a stream set.

    Components without a molecular formula (pseudo-components) carry mass only.
    """
    mass = 0.0
    atoms: dict[str, float] = {}
    for state in states:
        for cid, y in state.composition.items():
            n = state.molar_flow * y
            mass += n * float(component_record(cid)["mw"])
            try:
                formula = atomic_composition(cid)
            except MissingFormationData:
                continue
            for element, count in formula.items():
                atoms[element] = atoms.get(element, 0.0) + n * count
    return mass, atoms


def species_without_formation(states: Iterable[StreamState]) -> list[str]:
    """Sorted ids of the species present (y > 0) that have no formation enthalpy."""
    missing: set[str] = set()
    for state in states:
        for cid, y in state.composition.items():
            if y <= 0.0 or cid in missing:
                continue
            try:
                formation_enthalpy(cid, 298.15)
            except MissingFormationData:
                missing.add(cid)
    return sorted(missing)


def energy_basis(
    balance: str,
    inlets: Iterable[StreamState],
    outlets: Iterable[StreamState],
    info: Mapping[str, float],
) -> EnergyBasis:
    """The enthalpy basis a result must close on; raises when none is valid."""
    if balance != "mass_elements":
        return "sensible"
    missing = species_without_formation([*inlets, *outlets])
    if not missing:
        return "formation"
    if info.get(SENSIBLE_ONLY_FLAG):
        return "sensible_declared"
    raise BalanceBasisError(
        f"species {missing} have no formation enthalpy, and the unit does not set "
        f"info[{SENSIBLE_ONLY_FLAG!r}] to declare a sensible-only duty"
    )


def stream_enthalpy(states: Iterable[StreamState], basis: EnergyBasis) -> float:
    """Sum of stream enthalpy flows, J/s, on the given basis."""
    if basis == "formation":
        return sum(enthalpy_with_formation(s) for s in states)
    return sum(s.molar_flow * s.enthalpy for s in states)
