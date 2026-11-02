"""Reaction thermochemistry from the cited database.

Species models live in :mod:`ngdesign.data.species_models`; this module sums them
over reactions: ΔrH°, ΔrS°, ΔrG°, ln K, heating values and flame temperatures.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace

import scipy.constants as sc
from scipy.optimize import brentq

from ngdesign.chem.stoichiometry import Equation, Term, as_written, balance
from ngdesign.data import chemdb
from ngdesign.data.chemdb import MissingPropertyError
from ngdesign.data.formula import parse_formula
from ngdesign.data.species_models import (
    AQUEOUS,
    PHASES,
    REFERENCE,
    T_REF,
    SpeciesThermo,
    TemperatureRangeError,
    ThermochemError,
    _has_reference_table,
    _reference_state,
    species_thermo,
    stable_phase,
)
from ngdesign.uom.quantity import si_arguments

R = sc.R
P_STANDARD = 1.0e5


def _term_thermo(term: Term, T: float, hf_source: str | None) -> SpeciesThermo:
    query = term.species_query
    if query is None:
        raise ThermochemError(f"{term.key!r} has no species identity")
    if term.formula.charge and term.phase is None:
        term = replace(term, phase=AQUEOUS)  # an ion exists here only in water
    if term.phase == AQUEOUS:
        try:
            return species_thermo(query, AQUEOUS)
        except MissingPropertyError as exc:
            raise ThermochemError(f"{term.key!r}: {exc}") from exc
    if term.phase is None and _has_reference_table(chemdb.find(query).cas):
        return _reference_state(query)  # an element left unqualified means its standard state
    phase = term.phase if term.phase in PHASES else stable_phase(query, T) if term.phase is None else None
    if phase is None:
        raise ThermochemError(f"{term.key!r}: {term.phase} standard states are not supported")
    try:
        return species_thermo(query, phase, hf_source)
    except MissingPropertyError:
        if hf_source is None:
            raise
        return species_thermo(query, phase)


@dataclass(frozen=True)
class ReactionThermo:
    """Standard reaction properties at T, per mole of reaction as written."""

    equation: str
    T: float
    dH: float  # J/mol
    dS: float  # J/(mol K)
    dG: float  # J/mol
    dCp: float  # J/(mol K)
    lnK: float
    species: dict[str, SpeciesThermo]

    @property
    def K(self) -> float:
        return math.exp(self.lnK)

    @property
    def is_exothermic(self) -> bool:
        return self.dH < 0.0

    def provenance(self) -> dict[str, dict[str, str]]:
        """Which model and source produced each term."""
        return {key: {"phase": t.phase, **t.provenance} for key, t in self.species.items()}


@si_arguments(T="temperature")
def reaction_thermo(
    equation: str | Equation,
    T: float = T_REF,
    *,
    phases: Mapping[str, str] | None = None,
    hf_source: str | None = None,
) -> ReactionThermo:
    """ΔrH°, ΔrS°, ΔrG°, ΔrCp° and ln K of a reaction at T.

    ln K = −ΔrG°/(RT), with activities on 1 bar (gas) and pure-substance (condensed)
    standard states. A term's phase comes from ``phases`` (term key -> phase), else
    its ``(g)``/``(l)``/``(s)`` suffix, else the stable phase at T. Values are per mole
    of reaction as written; an unbalanced equation is balanced first.
    """
    balanced = as_written(equation)
    override = dict(phases or {})
    species: dict[str, SpeciesThermo] = {}
    dH = dS = dCp = 0.0
    for term, coefficient in zip(balanced.terms, balanced.coefficients, strict=True):
        nu = float(coefficient)
        if term.key in override:
            term = Term(term.label, term.formula, term.species_query, override[term.key])
        thermo = _term_thermo(term, T, hf_source)
        species[term.key] = thermo
        dH += nu * thermo.h(T)
        dS += nu * thermo.s(T)
        dCp += nu * thermo.cp(T)
    dG = dH - T * dS
    return ReactionThermo(str(balanced), T, dH, dS, dG, dCp, -dG / (R * T), species)


def kp_to_kc(K: float, delta_nu_gas: float, T: float) -> float:
    """K_c (mol/m3 basis) from K (1 bar standard state): K·(P°/(R·T))^Δν."""
    return float(K * (P_STANDARD / (R * T)) ** delta_nu_gas)


def equilibrium_temperature(
    equation: str | Equation, *, lower: float = 300.0, upper: float = 3000.0
) -> float:
    """The T where ΔrG°(T) = 0 (K = 1), the crossover of ΔH and TΔS."""
    balanced = as_written(equation)

    def gibbs(T: float) -> float:
        return reaction_thermo(balanced, T).dG

    if gibbs(lower) * gibbs(upper) > 0.0:
        raise ThermochemError(f"ΔrG° does not change sign on [{lower}, {upper}] K for {balanced}")
    return float(brentq(gibbs, lower, upper, xtol=1e-6))


@dataclass(frozen=True)
class HeatingValue:
    """Heat of complete combustion per mole and per mass of fuel."""

    fuel: str
    equation: str
    hhv_molar: float  # J/mol, product water liquid
    lhv_molar: float  # J/mol, product water vapour
    hhv_mass: float  # J/kg
    lhv_mass: float  # J/kg


def combustion_equation(query: str) -> Equation:
    """Complete combustion: C->CO2, H->H2O, S->SO2, N->N2; other elements refused."""
    species = chemdb.find(query)
    atoms = parse_formula(species.formula).composition
    extra = set(atoms) - {"C", "H", "O", "N", "S"}
    if extra:
        raise ThermochemError(f"complete combustion of {species.name} is undefined for {sorted(extra)}")
    products = [
        p for p, element in (("CO2", "C"), ("H2O", "H"), ("SO2", "S"), ("N2", "N")) if element in atoms
    ]
    equation = balance(f"{species.formula} + O2 -> {' + '.join(products)}")
    fuel = replace(equation.terms[0], species_query=species.cas)  # the formula alone may name isomers
    return replace(equation, terms=(fuel, *equation.terms[1:]))


def heating_value(query: str, *, fuel_phase: str | None = None) -> HeatingValue:
    """HHV and LHV at 298.15 K from Δ_cH° (positive numbers).

    The fuel is taken in its stable phase at 298.15 K unless ``fuel_phase`` says otherwise.
    """
    species = chemdb.find(query)
    if species.mw is None:
        raise ThermochemError(f"{species.name} has no molar mass")
    equation = combustion_equation(query)
    phase = fuel_phase or stable_phase(query, T_REF)
    fuel_key = equation.terms[0].key

    def heat(water: str) -> float:
        phases = {term.key: "gas" for term in equation.terms}
        phases[fuel_key] = phase
        if "H2O" in phases:
            phases["H2O"] = water
        return -reaction_thermo(equation, T_REF, phases=phases).dH / float(equation.reactants[fuel_key])

    hhv = heat("liquid")
    lhv = heat("gas")
    kg = species.mw * 1e-3
    return HeatingValue(species.name, str(equation), hhv, lhv, hhv / kg, lhv / kg)


def adiabatic_flame_temperature(
    fuel: str,
    *,
    phi: float = 1.0,
    T_in: float = T_REF,
    oxidant: Mapping[str, float] | None = None,
) -> float:
    """Constant-pressure adiabatic temperature of complete combustion, K (no dissociation).

    Solves Σ n_p H°_p(T_ad) = Σ n_r H°_r(T_in) for gas-phase reactants and products.
    ``oxidant`` is mole ratios per mole of O2, default the conventional 3.76 N2 of
    dry air (79/21 by volume). Lean only (φ ≤ 1): rich products need the equilibrium
    composition, which :func:`ngdesign.chem.equilibrium.adiabatic_equilibrium` gives.
    """
    if not 0.0 < phi <= 1.0:
        raise ThermochemError(
            "complete combustion needs 0 < phi <= 1; use adiabatic_equilibrium for rich mixtures"
        )
    air = {"N2": 3.76} if oxidant is None else {k: v for k, v in oxidant.items() if k != "O2"}
    equation = combustion_equation(fuel)
    fuel_key = equation.terms[0].key
    per_fuel = 1.0 / float(equation.reactants[fuel_key])
    o2_stoich = float(equation.reactants["O2"]) * per_fuel
    o2_feed = o2_stoich / phi
    reactants = {chemdb.find(fuel).cas: 1.0, "O2": o2_feed, **{k: o2_feed * v for k, v in air.items()}}
    products: dict[str, float] = {"O2": o2_feed - o2_stoich, **{k: o2_feed * v for k, v in air.items()}}
    for key, nu in equation.products.items():
        products[key] = products.get(key, 0.0) + float(nu) * per_fuel
    enthalpy_in = sum(n * species_thermo(k).h(T_in) for k, n in reactants.items())

    def residual(T: float) -> float:
        return sum(n * species_thermo(k).h(T) for k, n in products.items() if n > 0.0) - enthalpy_in

    return float(brentq(residual, max(T_in, T_REF), 6000.0, xtol=1e-6))


__all__ = [
    "P_STANDARD",
    "PHASES",
    "R",
    "REFERENCE",
    "T_REF",
    "HeatingValue",
    "ReactionThermo",
    "SpeciesThermo",
    "TemperatureRangeError",
    "ThermochemError",
    "adiabatic_flame_temperature",
    "combustion_equation",
    "equilibrium_temperature",
    "heating_value",
    "kp_to_kc",
    "reaction_thermo",
    "species_thermo",
    "stable_phase",
]
