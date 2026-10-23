"""Databank-backed standard formation properties (spec U-R).

All values SI: J, mol, K. Ideal-gas standard state at 1 bar. The ``thermo``
databank supplies ΔfH°298, ΔfG°298 and S°298 (gas); temperature dependence
rides the databank's JANAF ideal-gas Cp. Elemental species carry exactly zero
formation properties at every temperature, so reaction sums cancel the
element reference cleanly.

Measured against the installed databank: ``Chemical`` formation attributes are
mass-basis (J/kg, J/(kg K)); multiplying by the record molar flow (kg/mol)
converts to molar values - e.g. methane Hfg -4646045 J/kg x 0.016043 kg/mol =
-74542 J/mol, matching JANAF ΔfH°298 = -74.6 kJ/mol within 0.5 %.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from chemicals.elements import periodic_table, simple_formula_parser
from thermo.chemical import Chemical
from thermo.heat_capacity import HeatCapacityGas

from ngdesign.data import component_record

#: Reference temperature of the databank formation properties, K.
T_REF = 298.15

#: Atomic numbers of elements whose standard state is a homonuclear diatomic
#: molecule (H2, N2, O2, F2, Cl2, Br2, I2): one molecule carries two atoms.
_HOMONUCLEAR = {1, 7, 8, 9, 17, 35, 53}

#: S°298 of the elements in their standard states, J/(mol K), indexed by
#: atomic number - 1 (CRC/JANAF). Fallback for species the databank has no
#: gas-phase standard entropy for; homonuclear-diatomic entries are per molecule.
S0s: tuple[float | None, ...] = (
    None,
    130.68,
    None,
    None,
    5.90,
    5.74,
    None,
    191.61,
    205.15,
    202.79,
    None,
    146.33,
    51.21,
    32.68,
    28.30,
    18.81,
    41.09,
    31.88,
    223.08,
    154.85,
    64.18,
    41.42,
    None,
    30.63,
    None,
    None,
    23.62,
    32.01,
    27.28,
    30.04,
    29.87,
    33.15,
    41.63,
    152.21,
    None,
    116.14,
)


class MissingFormationData(ValueError):
    """Raised when the databank has no formation data for a component."""


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


@cache
def _formation_298(cid: str) -> tuple[float, float, float | None]:
    """(ΔfH°298, ΔfG°298, S°298|None) in J/mol from the databank.

    Raises :class:`MissingFormationData` when the component has no formula or
    the databank has no gas-phase formation enthalpy for it.
    """
    record = _record(cid)
    if not record.get("formula"):
        raise MissingFormationData(f"component {cid!r} has no formation data (no formula)")
    chemical = Chemical(str(record["cas"]))
    mw_kg = float(record["mw"]) / 1000.0
    if chemical.Hfg is None or chemical.Gfg is None:
        raise MissingFormationData(f"component {cid!r} has no databank formation enthalpy")
    hf = float(chemical.Hfg) * mw_kg
    gf = float(chemical.Gfg) * mw_kg
    s0 = float(chemical.S0g) * mw_kg if chemical.S0g is not None else None
    return hf, gf, s0


@cache
def _cpg_molar(cid: str) -> HeatCapacityGas | None:
    """The databank's temperature-dependent ideal-gas Cp accessor, or None."""
    record = _record(cid)
    try:
        return HeatCapacityGas(str(record["cas"]))
    except Exception:
        return None


def _cp_molar(cid: str, T: float) -> float:
    """Ideal-gas Cp at T, J/(mol K); 0.0 when the databank has no correlation."""
    accessor = _cpg_molar(cid)
    mw_kg = float(_record(cid)["mw"]) / 1000.0
    if accessor is None:
        return 0.0
    value = accessor.T_dependent_property(T)
    return float(value) * mw_kg if value is not None else 0.0


def _integrate_cp(cid: str, T: float, over_t: bool) -> float:
    """∫ Cp dT (over_t=False) or ∫ Cp/T dT (over_t=True) from T_REF to T, SI."""
    sign = 1.0
    t0, t1 = T_REF, T
    if T < T_REF:
        sign, t0, t1 = -1.0, T, T_REF
    steps = 400
    dt = (t1 - t0) / steps
    total = 0.0
    for i in range(steps + 1):
        t = t0 + dt * i
        cp = _cp_molar(cid, t)
        weight = 1.0 if i in (0, steps) else (4.0 if i % 2 == 1 else 2.0)
        total += weight * (cp / t if over_t else cp)
    return sign * total * dt / 3.0


def is_element(cid: str) -> bool:
    """True when the component is an element in its standard state (ΔfH = ΔfG = 0)."""
    try:
        hf, gf, _ = _formation_298(cid)
    except MissingFormationData:
        return False
    return hf == 0.0 and gf == 0.0 and len(atomic_composition(cid)) == 1


#: Element symbol -> atomic number, from the databank's periodic table.
_SYMBOL_NUMBERS: dict[str, int] = {element.symbol: element.number for element in periodic_table}


def _element_entropy(atoms: dict[str, int]) -> float:
    """Σ ν_el·S°(element) over the formula's elements, homonuclear-diatomic aware."""
    total = 0.0
    for element, count in atoms.items():
        number = _SYMBOL_NUMBERS.get(element)
        if number is None:
            raise MissingFormationData(f"formula element {element!r} is not in the element table")
        s0 = S0s[number - 1]
        if s0 is None:
            raise MissingFormationData(f"no standard entropy for element {element!r} in the table")
        coefficient = count / 2 if number in _HOMONUCLEAR else count
        total += coefficient * s0
    return total


def standard_entropy_298(cid: str) -> float:
    """S°298 of one component, J/(mol K): databank S°g when present, else the
    element-reference fallback S(elements) - ΔSf°298."""
    hf, gf, s0 = _formation_298(cid)
    if s0 is not None:
        return s0
    delta_s_formation = (hf - gf) / T_REF
    return _element_entropy(atomic_composition(cid)) - delta_s_formation


def formation_enthalpy(cid: str, T: float) -> float:
    """ΔfH°(cid, T), J/mol, ideal gas; identically 0 for elemental species."""
    if is_element(cid):
        return 0.0
    hf, _, _ = _formation_298(cid)
    return hf + _integrate_cp(cid, T, over_t=False)


def formation_gibbs(cid: str, T: float) -> float:
    """ΔfG°(cid, T), J/mol, ideal gas: ΔfH(T) − T·ΔfS(T).

    ΔfS°298 = (ΔfH°298 − ΔfG°298)/T_REF from the databank pair; the
    temperature dependence is ΔfS(T) = ΔfS°298 + ∫ Cp(cid)/T dT — i.e. element
    standard-state entropies are treated as temperature-independent. For
    balanced reactions the element terms cancel identically in Σν·ΔfG, so
    reaction equilibrium constants are unaffected by that approximation.
    Identically 0 for elemental species.
    """
    if is_element(cid):
        return 0.0
    hf, gf, _ = _formation_298(cid)
    if T == T_REF:
        return gf
    delta_s_formation_298 = (hf - gf) / T_REF
    enthalpy = hf + _integrate_cp(cid, T, over_t=False)
    entropy_formation = delta_s_formation_298 + _integrate_cp(cid, T, over_t=True)
    return enthalpy - T * entropy_formation
