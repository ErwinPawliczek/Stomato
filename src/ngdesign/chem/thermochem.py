"""Species and reaction thermochemistry from the cited database.

Every species gets a standard-state model on the element reference used by
NIST-JANAF: H°(298.15 K) = ΔfH°298, elements in their reference state at zero, S°
absolute, standard pressure 1 bar, ideal gas or pure condensed phase.

Models, best first, chosen per species and phase:

1. **NIST-JANAF table**. H°(T) − H°(298) and S°(T) are cubic Hermite interpolants
   with Cp and Cp/T as nodal slopes, so they reproduce the table at every node and
   stay consistent with dH = Cp dT between nodes.
2. **NIST Shomate** pieces (Chase 1998 form): with t = T/1000,
   Cp = A + Bt + Ct² + Dt³ + E/t²;
   H − H298 = At + Bt²/2 + Ct³/3 + Dt⁴/4 − E/t + F − H (kJ/mol);
   S = A ln t + Bt + Ct²/2 + Dt³/3 − E/(2t²) + G.
3. **Gas Cp fits**: TRC eight-term or Poling polynomial (evaluated with their
   ``chemicals`` integrals) on the selected S°298.
4. **Constant Cp** at the tabulated 298 K value, for condensed species only. The
   result names itself ``constant_cp`` so the coarser model stays visible.

A temperature outside a model's range is refused, never extrapolated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

import numpy as np
import scipy.constants as sc
from chemicals.heat_capacity import (
    Poling,
    Poling_integral,
    Poling_integral_over_T,
    TRCCp,
    TRCCp_integral,
    TRCCp_integral_over_T,
)
from scipy.optimize import brentq

from ngdesign.chem.formula import parse_formula
from ngdesign.chem.stoichiometry import Equation, Term, as_written, balance
from ngdesign.data import chemdb
from ngdesign.data.chemdb import MissingPropertyError
from ngdesign.uom.quantity import si_arguments

R = sc.R
T_REF = 298.15
P_STANDARD = 1.0e5
PHASES = ("gas", "liquid", "solid")
REFERENCE = "reference"  # an element's reference state, whatever phase it is in at T


class ThermochemError(ValueError):
    """Base class of thermochemistry refusals."""


class TemperatureRangeError(ThermochemError):
    """A temperature lies outside the validity range of the species model."""


class _Curve:
    """H°(T) − H°298 and S°(T) evaluation of one model."""

    tmin: float
    tmax: float
    name: str

    def cp(self, T: float) -> float:
        raise NotImplementedError

    def dh(self, T: float) -> float:
        raise NotImplementedError

    def s(self, T: float) -> float:
        raise NotImplementedError


class _JanafCurve(_Curve):
    """Cubic Hermite through a JANAF table; transitions are jumps between nodes."""

    def __init__(self, rows: Sequence[Mapping[str, Any]], table: str) -> None:
        self.t = np.array([float(r["T"]) for r in rows])
        self.cp_nodes = np.array([float(r["Cp"]) for r in rows])
        self.h_nodes = np.array([float(r["H_H298"]) for r in rows])
        self.s_nodes = np.array([float(r["S"]) for r in rows])
        self.tmin = float(self.t[0])
        self.tmax = float(self.t[-1])
        self.name = f"janaf:{table}"

    def _interval(self, T: float) -> tuple[int, float, float]:
        i = int(np.searchsorted(self.t, T, side="right")) - 1
        i = max(0, min(i, len(self.t) - 2))
        width = float(self.t[i + 1] - self.t[i])
        if width == 0.0:  # a transition sits on this node: step into the next interval
            i += 1
            width = float(self.t[i + 1] - self.t[i])
        return i, width, (T - float(self.t[i])) / width

    def cp(self, T: float) -> float:
        i, _, u = self._interval(T)
        return float(self.cp_nodes[i] + u * (self.cp_nodes[i + 1] - self.cp_nodes[i]))

    @staticmethod
    def _hermite(y0: float, y1: float, m0: float, m1: float, h: float, u: float) -> float:
        h00 = 2 * u**3 - 3 * u**2 + 1
        h10 = u**3 - 2 * u**2 + u
        h01 = -2 * u**3 + 3 * u**2
        h11 = u**3 - u**2
        return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1

    def dh(self, T: float) -> float:
        i, h, u = self._interval(T)
        return self._hermite(
            float(self.h_nodes[i]),
            float(self.h_nodes[i + 1]),
            float(self.cp_nodes[i]),
            float(self.cp_nodes[i + 1]),
            h,
            u,
        )

    def s(self, T: float) -> float:
        i, h, u = self._interval(T)
        return self._hermite(
            float(self.s_nodes[i]),
            float(self.s_nodes[i + 1]),
            float(self.cp_nodes[i] / self.t[i]),
            float(self.cp_nodes[i + 1] / self.t[i + 1]),
            h,
            u,
        )


class _ShomateCurve(_Curve):
    """Piecewise NIST Shomate fit. Table windows open at 298, treated as 298.15."""

    def __init__(self, pieces: Sequence[Mapping[str, Any]]) -> None:
        self.pieces = sorted(pieces, key=lambda p: float(p["Tmin"]))
        self.tmin = float(self.pieces[0]["Tmin"])
        self.tmax = float(self.pieces[-1]["Tmax"])
        self.name = "shomate"

    def _piece(self, T: float) -> Mapping[str, Any]:
        for piece in self.pieces:
            if T <= float(piece["Tmax"]):
                return piece
        return self.pieces[-1]

    def cp(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        return float(c["A"] + c["B"] * t + c["C"] * t**2 + c["D"] * t**3 + c["E"] / t**2)

    def dh(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        kj = (
            c["A"] * t
            + c["B"] * t**2 / 2
            + c["C"] * t**3 / 3
            + c["D"] * t**4 / 4
            - c["E"] / t
            + c["F"]
            - c["H"]
        )
        return float(kj) * 1000.0

    def s(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        return float(
            c["A"] * math.log(t)
            + c["B"] * t
            + c["C"] * t**2 / 2
            + c["D"] * t**3 / 3
            - c["E"] / (2 * t**2)
            + c["G"]
        )


class _PolyCurve(_Curve):
    """Gas Cp fit in the TRC or Poling form, anchored on S°298."""

    def __init__(self, fit: Mapping[str, Any], s298: float) -> None:
        self.form = str(fit["form"])
        self.tmin = float(fit["Tmin"])
        self.tmax = float(fit["Tmax"])
        self.name = f"cp_fit:{self.form}"
        count = 8 if self.form == "trc" else 5
        self.a = tuple(float(fit[f"a{i}"]) for i in range(count))
        self.s298 = s298

    def cp(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp(T, *self.a))
        return float(Poling(T, *self.a))  # type: ignore[no-untyped-call]

    def _h(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp_integral(T, *self.a))
        return float(Poling_integral(T, *self.a))  # type: ignore[no-untyped-call]

    def _s(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp_integral_over_T(T, *self.a))
        return float(Poling_integral_over_T(T, *self.a))  # type: ignore[no-untyped-call]

    def dh(self, T: float) -> float:
        return self._h(T) - self._h(T_REF)

    def s(self, T: float) -> float:
        return self.s298 + self._s(T) - self._s(T_REF)


class _ConstantCpCurve(_Curve):
    """Constant Cp between stated limits: the coarse condensed-phase fallback."""

    def __init__(self, cp: float, s298: float, tmin: float, tmax: float) -> None:
        self._cp = cp
        self.s298 = s298
        self.tmin = tmin
        self.tmax = tmax
        self.name = "constant_cp"

    def cp(self, T: float) -> float:
        return self._cp

    def dh(self, T: float) -> float:
        return self._cp * (T - T_REF)

    def s(self, T: float) -> float:
        return self.s298 + self._cp * math.log(T / T_REF)


@dataclass(frozen=True)
class SpeciesThermo:
    """Standard-state thermochemistry of one species in one phase. SI: J, mol, K."""

    cas: str
    name: str
    phase: str
    hf298: float
    curve: _Curve
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return self.curve.name

    @property
    def t_range(self) -> tuple[float, float]:
        return self.curve.tmin, self.curve.tmax

    def _check(self, T: float) -> float:
        if T < self.curve.tmin - 0.16 or T > self.curve.tmax:
            raise TemperatureRangeError(
                f"{self.name} ({self.phase}): {T} K is outside the {self.curve.name} range "
                f"[{self.curve.tmin}, {self.curve.tmax}] K"
            )
        return max(T, self.curve.tmin)

    def cp(self, T: float) -> float:
        """Cp°(T), J/(mol K)."""
        return self.curve.cp(self._check(T))

    def h(self, T: float) -> float:
        """H°(T) = ΔfH°298 + [H°(T) − H°298], J/mol."""
        return self.hf298 + self.curve.dh(self._check(T))

    def s(self, T: float) -> float:
        """S°(T), J/(mol K)."""
        return self.curve.s(self._check(T))

    def g(self, T: float) -> float:
        """G°(T) = H°(T) − T·S°(T), J/mol (the Gibbs energy function on the element reference)."""
        return self.h(T) - T * self.s(T)


def _janaf_rows(cas: str, phase: str) -> tuple[list[dict[str, Any]], str] | None:
    """The best single-phase JANAF rows of a species: a table that holds 298.15 K.

    A composite table is cut where it leaves the requested phase, so a solid never
    silently melts. Solid-solid transitions stay inside the solid.
    """
    tables = chemdb.janaf(cas)
    candidates: list[tuple[float, int, int, str, list[dict[str, Any]]]] = []
    for table, rows in tables.items():
        if phase == "reference":
            return (list(rows), table) if rows[0]["phase"] == "ref" else None
        label = str(rows[0]["phase"])
        phase_298 = str(rows[0]["phase_298"])
        rank: int | None = None
        if phase == "gas" and (label == "g" or (label == "ref" and phase_298 == "gas")):
            rank = 1 if label == "ref" else 0
        elif phase == "liquid" and (label == "l" or (label == "ref" and phase_298 == "liquid")):
            rank = 0
        elif phase == "solid" and (label in ("cr", "cr,l") or (label == "ref" and phase_298 == "solid")):
            rank = {"ref": 0, "cr": 1, "cr,l": 2}[label]
        if rank is None:
            continue
        window = _phase_window(rows, phase)
        at_298 = next((r for r in window if float(r["T"]) == T_REF), None)
        if at_298 is not None and at_298["Hf"] is not None:
            # the stable polymorph has the lowest G°298, however long its table runs
            gibbs = float(at_298["Hf"]) - T_REF * float(at_298["S"])
            candidates.append((round(gibbs, 3), rank, -len(window), table, window))
    if not candidates:
        return None
    _, _, _, table, window = min(candidates, key=lambda c: c[:4])
    return window, table


def _phase_window(rows: Sequence[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    """Rows of a table up to the transition that leaves ``phase``."""
    out: list[dict[str, Any]] = []
    stop = "<--> IDEAL GAS" if phase == "liquid" else "<--> LIQUID"
    for row in rows:
        out.append(row)
        note = str(row.get("note") or "").upper()
        if phase == "gas":
            continue
        if stop in note or (phase == "solid" and "<--> IDEAL GAS" in note):
            break
    return out


def _standard_entropy(cas: str, phase: str, hf: float) -> tuple[float, str]:
    """S°298: stated, else (ΔfH° − ΔfG°)/298.15 + Σ S°(elements), which ΔfS° defines."""
    stated = chemdb.values(cas, f"S0_{phase}")
    if stated:
        row = next(r for r in stated if r.selected)
        return row.value, row.source
    gibbs = chemdb.maybe(cas, f"Gf_{phase}")
    if gibbs is None:
        raise MissingPropertyError(f"no source states S° or ΔfG° for {cas} ({phase})")
    elements = 0.0
    for element, count in parse_formula(chemdb.find(cas).formula).atoms:
        reference = _element_reference(element)
        atoms = reference.atoms_per_molecule
        elements += count / atoms * reference.thermo.s(T_REF)
    return (hf - gibbs) / T_REF + elements, "derived from ΔfG° and element S°"


@dataclass(frozen=True)
class _ElementReference:
    thermo: SpeciesThermo
    atoms_per_molecule: int


@lru_cache(maxsize=128)
def _element_reference(symbol: str) -> _ElementReference:
    """The JANAF reference-state species of an element (N -> N2, C -> graphite, ...)."""
    for formula, atoms in ((symbol, 1), (f"{symbol}2", 2)):
        for species in chemdb.by_formula(formula):
            for table in chemdb.janaf(species.cas).values():
                if table[0]["phase"] == "ref":
                    phase = str(table[0]["phase_298"])
                    return _ElementReference(species_thermo(species.cas, phase), atoms)
    raise MissingPropertyError(f"no reference-state table for element {symbol}")


@lru_cache(maxsize=4096)
def species_thermo(query: str, phase: str = "gas", hf_source: str | None = None) -> SpeciesThermo:
    """The standard-state model of a species in ``phase``; see the module docstring.

    ``hf_source`` pins ΔfH°298 to one source (e.g. ``"janaf"``, to reproduce that
    table exactly) instead of the selected value.
    """
    if phase == REFERENCE:
        return _reference_state(query)
    if phase not in PHASES:
        raise ThermochemError(f"phase must be one of {PHASES}, got {phase!r}")
    species = chemdb.find(query)
    rows = chemdb.values(species.cas, f"Hf_{phase}")
    if hf_source is not None:
        rows = [r for r in rows if r.source == hf_source]
    chosen = next((r for r in rows if r.selected), rows[0] if rows else None)
    if chosen is None:
        raise MissingPropertyError(
            f"no ΔfH° for {species.name} ({phase})" + (f" from {hf_source}" if hf_source else "")
        )
    hf = chosen.value
    provenance = {"hf298": f"{chosen.source} [{chosen.grade}] {chosen.reference}".strip()}
    curve: _Curve | None = None
    janaf = _janaf_rows(species.cas, phase)
    if janaf is not None:
        curve = _JanafCurve(janaf[0], janaf[1])
        if chosen.source == "janaf":
            # enthalpy and shape from one table: polymorphs differ in both
            hf = next(float(r["Hf"]) for r in janaf[0] if float(r["T"]) == T_REF)
            provenance["hf298"] = f"janaf [{chosen.grade}] JANAF table {janaf[1]}"
    else:
        pieces = chemdb.shomate(species.cas, phase)
        if pieces:
            curve = _ShomateCurve(pieces)
    if curve is None:
        s298, s_source = _standard_entropy(species.cas, phase, hf)
        provenance["s298"] = s_source
        if phase == "gas":
            fits = chemdb.cp_gas(species.cas)
            fit = next((f for f in fits if f["form"] == "trc"), fits[0] if fits else None)
            if fit is not None:
                curve = _PolyCurve(fit, s298)
        if curve is None:
            cp = chemdb.maybe(species.cas, f"Cp_{phase}")
            if cp is None:
                raise MissingPropertyError(f"no Cp(T) data for {species.name} ({phase})")
            if phase == "gas":
                tmin, tmax = T_REF, T_REF + 100.0
            elif phase == "liquid":
                tmin = chemdb.maybe(species.cas, "Tm") or 200.0
                tmax = chemdb.maybe(species.cas, "Tb") or T_REF + 100.0
            else:
                tmin = 100.0
                tmax = chemdb.maybe(species.cas, "Tm") or T_REF + 100.0
            curve = _ConstantCpCurve(cp, s298, min(tmin, T_REF), max(tmax, T_REF))
    provenance["shape"] = curve.name
    return SpeciesThermo(species.cas, species.name, phase, hf, curve, provenance)


def _reference_state(query: str) -> SpeciesThermo:
    """An element's whole JANAF reference table, phase changes included, H°298 = 0.

    Above boiling this is the *reference* vapour, which for sulfur and phosphorus is
    not the atomic gas their CAS names: JANAF's reference continues as S2, so
    ``species_thermo("S", "gas")`` (monatomic) would be the wrong substance.
    """
    species = chemdb.find(query)
    janaf = _janaf_rows(species.cas, REFERENCE)
    if janaf is None:
        raise MissingPropertyError(f"{species.name} has no JANAF reference-state table")
    curve = _JanafCurve(janaf[0], janaf[1])
    return SpeciesThermo(
        species.cas, species.name, REFERENCE, 0.0, curve, {"hf298": "element", "shape": curve.name}
    )


def _has_reference_table(cas: str) -> bool:
    return any(rows[0]["phase"] == "ref" for rows in chemdb.janaf(cas).values())


def stable_phase(query: str, T: float) -> str:
    """The stable phase at (T, 1 bar), from the reference table or Tm and Tb.

    A species with no melting or boiling data, or no ΔfH° in that phase, falls to
    the nearest phase that has one, gas first.
    """
    species = chemdb.find(query)
    for table in chemdb.janaf(species.cas).values():
        if table[0]["phase"] == "ref":
            transitions = [row for row in table if "<-->" in str(row.get("note") or "")]
            for row in transitions:
                if float(row["T"]) >= T:
                    left = str(row["note"]).split("<-->")[0].strip().upper()
                    if left.startswith("LIQUID"):
                        return "liquid"
                    return "gas" if left.startswith("IDEAL GAS") else "solid"
            return "gas" if transitions else str(table[0]["phase_298"])
    tb = chemdb.maybe(species.cas, "Tb")
    tm = chemdb.maybe(species.cas, "Tm")
    if tb is not None and T >= tb:
        preferred = ["gas", "liquid", "solid"]
    elif tm is not None and T >= tm:
        preferred = ["liquid", "solid", "gas"]
    elif tm is not None:
        preferred = ["solid", "liquid", "gas"]
    elif tb is not None:
        preferred = ["liquid", "gas", "solid"]
    else:
        preferred = ["gas", "liquid", "solid"]
    for phase in preferred:
        if chemdb.maybe(species.cas, f"Hf_{phase}") is not None:
            return phase
    raise MissingPropertyError(f"no ΔfH° in any phase for {species.name}")


def _term_thermo(term: Term, T: float, hf_source: str | None) -> SpeciesThermo:
    query = term.species_query
    if query is None:
        raise ThermochemError(f"{term.key!r}: ions have no standard-state model here")
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
