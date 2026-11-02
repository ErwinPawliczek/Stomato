"""Standard formation properties from the cited chemical database (spec U-R, C-02).

All values SI: J, mol, K. Ideal-gas standard state at 1 bar. ΔfH°298, S°298 and the
temperature dependence all come from one :mod:`ngdesign.data.species_models` model of
the species, so they cannot come from mismatched tables, and every number traces to a
source in ``data/chemdb/sources.yaml``. Elemental species carry exactly zero formation
properties at every temperature, so reaction sums cancel the element reference
cleanly. A species the database has no gas-phase model for raises
:class:`MissingFormationData`; nothing is estimated here.
"""

from __future__ import annotations

from typing import Any

from chemicals.elements import simple_formula_parser

from ngdesign.data import chemdb, component_record
from ngdesign.data.species_models import (
    T_REF,
    SpeciesThermo,
    _element_reference,
    species_thermo,
)


class MissingFormationData(ValueError):
    """Raised when the database has no formation data for a component."""


def _record(cid: str) -> dict[str, Any]:
    try:
        return component_record(cid)
    except ValueError as exc:
        raise MissingFormationData(str(exc)) from exc


def atomic_composition(cid: str) -> dict[str, int]:
    """Element atom counts of one component's molecular formula."""
    record = _record(cid)
    formula = record.get("formula")
    if not formula:
        raise MissingFormationData(f"component {cid!r} has no molecular formula")
    return {el: int(n) for el, n in simple_formula_parser(str(formula)).items()}


def gas_model(cid: str) -> SpeciesThermo:
    """The ideal-gas model of one component, resolved by its CAS number."""
    record = _record(cid)
    if not record.get("formula") or not record.get("cas"):
        raise MissingFormationData(f"component {cid!r} has no formation data (no formula)")
    try:
        return species_thermo(str(record["cas"]), "gas")
    except chemdb.ChemDbError as exc:
        raise MissingFormationData(f"component {cid!r}: {exc}") from exc


def _element_entropy(atoms: dict[str, int]) -> float:
    """Σ ν_el·S°(element) over a formula, on the JANAF reference states."""
    total = 0.0
    for element, count in atoms.items():
        try:
            reference = _element_reference(element)
        except chemdb.ChemDbError as exc:
            raise MissingFormationData(str(exc)) from exc
        total += count / reference.atoms_per_molecule * reference.thermo.s(T_REF)
    return total


def _formation_gibbs_298(cid: str) -> float:
    """ΔfG°298 = ΔfH°298 − 298.15·(S°298 − Σ S°elements), J/mol."""
    model = gas_model(cid)
    return model.hf298 - T_REF * (model.s(T_REF) - _element_entropy(atomic_composition(cid)))


def is_element(cid: str) -> bool:
    """True when the component is an element in its standard state (ΔfH = 0)."""
    try:
        model = gas_model(cid)
        atoms = atomic_composition(cid)
    except MissingFormationData:
        return False
    return model.hf298 == 0.0 and len(atoms) == 1


def standard_entropy_298(cid: str) -> float:
    """S°298 of one component, J/(mol K)."""
    return gas_model(cid).s(T_REF)


def formation_enthalpy_298(cid: str) -> float:
    """ΔfH°298 of one component, J/mol; exactly 0.0 for elemental species.

    Used to anchor the reaction-path ΔrG°(T) assembly (see kinetics.ln_keq).
    """
    return 0.0 if is_element(cid) else gas_model(cid).hf298


def enthalpy_datum(cid: str) -> float:
    """J/mol added to a stream's package enthalpy to reach the element reference.

    The gas ΔfH°298 for anything with a gas model, which is every species a package
    can flash. A species that exists here only as a condensed phase (CaCO3, Fe2O3) has
    no gas datum, so it takes its stable condensed ΔfH°298; a stream carrying it states
    its enthalpy against that value.
    """
    try:
        return formation_enthalpy_298(cid)
    except MissingFormationData:
        record = _record(cid)
        if record.get("cas"):
            for phase in ("solid", "liquid"):
                value = chemdb.maybe(str(record["cas"]), f"Hf_{phase}")
                if value is not None:
                    return value
        raise


def integral_cp(cid: str, T: float, over_t: bool) -> float:
    """∫Cp dT (``over_t`` False) or ∫Cp/T dT (True) from 298.15 K to T, SI."""
    model = gas_model(cid)
    if over_t:
        return model.s(T) - model.s(T_REF)
    return model.h(T) - model.hf298


def formation_enthalpy(cid: str, T: float) -> float:
    """ΔfH°(cid, T), J/mol, ideal gas; identically 0 for elemental species."""
    return 0.0 if is_element(cid) else gas_model(cid).h(T)


def formation_gibbs(cid: str, T: float) -> float:
    """ΔfG°(cid, T), J/mol, ideal gas: ΔfH(T) − T·ΔfS(T).

    ΔfS°298 follows from S°298 and the elements' S°298; the temperature dependence
    is ΔfS(T) = ΔfS°298 + ∫ Cp(cid)/T dT, i.e. element standard-state entropies
    are treated as temperature-independent. For balanced reactions the element terms
    cancel identically in Σν·ΔfG; equilibrium constants themselves ride the reaction
    path in ``kinetics.ln_keq``, which needs no per-species ΔfG(T).
    Identically 0 for elemental species.
    """
    if is_element(cid):
        return 0.0
    gf = _formation_gibbs_298(cid)
    if T == T_REF:
        return gf
    model = gas_model(cid)
    delta_s_formation_298 = (model.hf298 - gf) / T_REF
    return model.h(T) - T * (delta_s_formation_298 + model.s(T) - model.s(T_REF))
